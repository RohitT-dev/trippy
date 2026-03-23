"""CrewAI Flow for Travel Planning State Machine"""

import asyncio
import json
import os
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from crewai.flow.flow import Flow, listen, start, or_
from crewai.flow.human_feedback import human_feedback

# Load .env so OLLAMA_MODEL is available when decorator arguments are evaluated
# flow.py lives in server/src/, so parents[1] == server/
load_dotenv(Path(__file__).parents[1] / ".env")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b").strip()
_FEEDBACK_LLM = f"ollama/{_OLLAMA_MODEL}"

from .schema import TravelState, ConfirmedDateRange, ItineraryDay, Itinerary
from .agents import TravelCrews
from .listeners.websocket_listener import broadcast
from . import feedback as _feedback_mod

logger = logging.getLogger(__name__)


def _extract_activities(text: str) -> List[str]:
    """Extract bullet-point or numbered activity lines from a text block."""
    activities = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r'^[-*•]|^\d+[.)\s]', line) and len(line) > 5:
            clean = re.sub(r'^[-*•\d.)\s]+', '', line).strip()
            if clean:
                activities.append(clean)
        elif line and len(line) > 10 and not line.startswith('#'):
            activities.append(line)
    return activities[:6]


def _parse_dates_from_text(text: str) -> Optional[ConfirmedDateRange]:
    """Extract the first two ISO dates from agent output and build a ConfirmedDateRange."""
    dates = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if len(dates) >= 2:
        try:
            start = datetime.fromisoformat(dates[0])
            end = datetime.fromisoformat(dates[1])
            duration = (end - start).days
            if duration > 0:
                return ConfirmedDateRange(
                    start_date=start,
                    end_date=end,
                    duration_days=duration,
                )
        except Exception:
            pass
    return None


def _parse_multiple_date_ranges(text: str) -> List[ConfirmedDateRange]:
    """Parse up to 4 unique 'YYYY-MM-DD to/– YYYY-MM-DD' pairs from agent output."""
    ranges: List[ConfirmedDateRange] = []
    pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2})'
        r'(?:\s+to\s+|\s*[-\u2013]\s*)'
        r'(\d{4}-\d{2}-\d{2})',
        re.IGNORECASE,
    )
    seen: set = set()
    for m in pattern.finditer(text):
        key = (m.group(1), m.group(2))
        if key in seen:
            continue
        seen.add(key)
        try:
            start = datetime.fromisoformat(m.group(1))
            end   = datetime.fromisoformat(m.group(2))
            duration = (end - start).days
            if duration > 0:
                ranges.append(ConfirmedDateRange(
                    start_date=start,
                    end_date=end,
                    duration_days=duration,
                ))
        except Exception:
            continue
        if len(ranges) == 4:
            break
    return ranges


def _parse_date_options_with_rationale(text: str) -> List[dict]:
    """Parse up to 4 Option-formatted date ranges and capture the rationale text.

    Matches lines like:
        Option 2: 2026-07-05 to 2026-07-19 (14 days) - Great festival season
    Falls back to bare YYYY-MM-DD pairs when the structured format is absent.
    """
    options: List[dict] = []
    structured = re.compile(
        r'Option\s*\d+[:\s]+'
        r'(\d{4}-\d{2}-\d{2})'
        r'(?:\s+to\s+|\s*[-\u2013]\s*)'
        r'(\d{4}-\d{2}-\d{2})'
        r'(?:\s*\(\d+\s*days?\))?'
        r'(?:\s*[-\u2013:]\s*([^\n]+))?',
        re.IGNORECASE,
    )
    for m in structured.finditer(text):
        try:
            start = datetime.fromisoformat(m.group(1))
            end   = datetime.fromisoformat(m.group(2))
            duration = (end - start).days
            if duration > 0:
                options.append({
                    "start": m.group(1),
                    "end": m.group(2),
                    "duration_days": duration,
                    "rationale": (m.group(3) or "").strip(),
                })
        except Exception:
            continue
        if len(options) == 4:
            break

    # Fallback: bare date pairs (no rationale)
    if not options:
        for cr in _parse_multiple_date_ranges(text):
            options.append({
                "start": cr.start_date.strftime("%Y-%m-%d"),
                "end": cr.end_date.strftime("%Y-%m-%d"),
                "duration_days": cr.duration_days,
                "rationale": "",
            })
    return options


def _parse_duration_days(duration_str: str) -> Optional[int]:
    """Parse a rough duration string to a number of days.

    '2 weeks' → 14, '10 days' → 10, '1 month' → 30, '3 nights' → 3
    """
    if not duration_str:
        return None
    s = duration_str.lower().strip()
    m = re.search(r'(\d+)\s*(?:day|night)', s)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*week', s)
    if m:
        return int(m.group(1)) * 7
    m = re.search(r'(\d+)\s*month', s)
    if m:
        return int(m.group(1)) * 30
    return None


def _find_cross_destination_windows(
    per_dest_options: dict,
    requested_days: Optional[int] = None,
) -> List[dict]:
    """Find up to 4 date windows that work for ALL destinations.

    Steps:
    1. Intersect per-destination option windows to find seasons suitable
       for every location simultaneously.
    2. For each overlapping region, slide `requested_days`-long windows
       across it to generate evenly-spaced options of exactly the right
       duration.  Falls back to the first destination's options when no
       cross-destination overlap exists.
    """
    dest_names = list(per_dest_options.keys())
    if not dest_names:
        return []

    def _to_dt(iso: str) -> datetime:
        return datetime.fromisoformat(iso)

    def _make_window(start: datetime, rationale: str) -> dict:
        """Build an option dict anchored at *start* with the requested length."""
        if requested_days:
            end = start + timedelta(days=requested_days)
            days = requested_days
        else:
            # No duration constraint — shouldn't normally reach here for rough dates
            end = start + timedelta(days=14)
            days = 14
        return {
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "duration_days": days,
            "rationale": rationale,
        }

    # Single destination — slide across its options to get 4 windows
    if len(dest_names) == 1:
        raw = per_dest_options[dest_names[0]][:4]
        if not requested_days:
            return [dict(o) for o in raw]
        results: List[dict] = []
        for o in raw:
            results.append(_make_window(_to_dt(o["start"]), o.get("rationale", "")))
        return results

    # ── Step 1: intersect windows across destinations ─────────────────────────
    candidates: List[dict] = [dict(o) for o in per_dest_options[dest_names[0]]]

    for dest_name in dest_names[1:]:
        dest_opts = per_dest_options[dest_name]
        merged: List[dict] = []
        for cand in candidates:
            c_start = _to_dt(cand["start"])
            c_end   = _to_dt(cand["end"])
            for dopt in dest_opts:
                d_start = _to_dt(dopt["start"])
                d_end   = _to_dt(dopt["end"])
                overlap_start = max(c_start, d_start)
                overlap_end   = min(c_end, d_end)
                if overlap_end > overlap_start:
                    parts = [
                        r for r in (cand.get("rationale", ""), dopt.get("rationale", "")) if r
                    ]
                    merged.append({
                        "start": overlap_start.strftime("%Y-%m-%d"),
                        "end":   overlap_end.strftime("%Y-%m-%d"),
                        "duration_days": (overlap_end - overlap_start).days,
                        "rationale": " | ".join(parts),
                    })
        if merged:
            candidates = merged
        # else: keep previous best-effort candidates

    # Deduplicate regions, longest first
    seen_regions: set = set()
    regions: List[dict] = []
    for c in sorted(candidates, key=lambda x: x["duration_days"], reverse=True):
        key = (c["start"], c["end"])
        if key not in seen_regions:
            seen_regions.add(key)
            regions.append(c)

    # ── Step 2: slide requested-duration windows across each region ───────────
    # For every overlapping region, generate evenly-spaced start dates so that
    # we fill up to 4 suggestions, each exactly `requested_days` long.
    if not requested_days:
        return regions[:4] or [dict(o) for o in per_dest_options[dest_names[0]][:4]]

    options: List[dict] = []
    seen_starts: set = set()
    needed = 4

    for region in regions:
        if len(options) >= needed:
            break
        r_start = _to_dt(region["start"])
        r_end   = _to_dt(region["end"])
        region_span = (r_end - r_start).days
        still_needed = needed - len(options)

        if region_span < requested_days:
            # Region shorter than trip duration — offer the region start anyway
            key = region["start"]
            if key not in seen_starts:
                seen_starts.add(key)
                options.append(_make_window(r_start, region.get("rationale", "")))
        else:
            # Slide `still_needed` windows evenly across the region
            # e.g. region = 60 days, requested = 14 → offsets 0, 15, 30, 45
            max_offset = region_span - requested_days
            step = max_offset // still_needed if still_needed > 1 else max_offset
            for i in range(still_needed):
                offset = min(i * step, max_offset)
                start = r_start + timedelta(days=offset)
                key = start.strftime("%Y-%m-%d")
                if key not in seen_starts:
                    seen_starts.add(key)
                    options.append(_make_window(start, region.get("rationale", "")))
                if len(options) >= needed:
                    break

    # Fallback: use first destination's options with requested duration enforced
    if not options:
        for o in per_dest_options[dest_names[0]][:4]:
            options.append(_make_window(_to_dt(o["start"]), o.get("rationale", "")))

    return options[:4]


def _build_cross_destination_analysis(
    merged_options: List[dict],
    dest_names: List[str],
) -> str:
    """Render merged windows in the standard 'Option N: …' format."""
    lines: List[str] = []
    if len(dest_names) > 1:
        lines.append(
            f"Cross-destination date analysis for: {', '.join(dest_names)}\n"
            "The following windows are suitable for ALL destinations simultaneously.\n"
        )
    for i, opt in enumerate(merged_options, 1):
        line = f"Option {i}: {opt['start']} to {opt['end']} ({opt['duration_days']} days)"
        if opt.get("rationale"):
            line += f" - {opt['rationale']}"
        lines.append(line)
    return "\n".join(lines)


class TravelPlannerFlow(Flow[TravelState]):
    """
    Main flow orchestrating the travel planning process.

    State transitions:
    pending → researching → awaiting_user → finalizing → complete
    """

    def __init__(self, initial_state: Optional[TravelState] = None):
        if initial_state is not None:
            self.initial_state = initial_state
        super().__init__()

    # ------------------------------------------------------------------
    # Override CrewAI's default terminal-input feedback with our queue.
    # CrewAI's kickoff() runs in a ThreadPoolExecutor thread, so
    # thread-local storage set on the *outer* thread is not visible here.
    # Reading session_id from self.state works from any thread.
    # ------------------------------------------------------------------
    def _request_human_feedback(self, message, output, metadata=None, emit=None) -> str:  # type: ignore[override]
        return _feedback_mod.wait_for_feedback(self.state.session_id)

    def _collapse_to_outcome(self, feedback: str, outcomes, llm=None) -> str:  # type: ignore[override]
        """Bypass the LLM classification round-trip.

        CrewAI 1.x calls this to map free-form feedback text to one of the
        emit outcome strings via an Ollama LLM call.  That call can block
        indefinitely if Ollama is busy with the main agent crews.

        Instead: the frontend always sends one of the exact emit strings
        (e.g. "dates_confirmed"), so a fast substring/exact match is enough.
        Falls back to the first outcome (the approval path) if nothing matches.
        """
        fb = feedback.strip().lower()
        # Exact match — frontend sends the outcome string directly
        for outcome in outcomes:
            if outcome.lower() == fb:
                return outcome
        # Substring match — covers "confirm dates_confirmed …" style texts
        for outcome in outcomes:
            if outcome.lower() in fb:
                return outcome
        # Default: first emit item is always the approval / continue path
        logger.debug(
            "_collapse_to_outcome: '%s' unmatched against %s; defaulting to '%s'",
            feedback, list(outcomes), outcomes[0],
        )
        return outcomes[0]

    @start()
    def initialize_flow(self) -> None:
        """Entry point: Validate inputs and initialize state"""
        logger.info(f"Starting travel planning for session {self.state.session_id}")
        self.state.ui_status = "researching"
        self.state.current_step = "interpreting_trip"

    @listen(initialize_flow)
    def interpret_trip(self) -> None:
        """Step 0: TripInterpreter reads the user\'s own words and preferences and
        produces a rich, structured trip outline that every downstream step can use.
        Skipped when no trip_description was provided.
        """
        description = (self.state.trip_description or "").strip()
        preferences = self.state.preferences

        # Build a compact preference + profile summary
        profile_parts = []
        if self.state.user_name:
            profile_parts.append(self.state.user_name)
        if self.state.user_age:
            profile_parts.append(f"age {self.state.user_age}")
        profile_str = f"Traveller: {', '.join(profile_parts)}. " if profile_parts else ""

        dest_names = ", ".join(d.name for d in self.state.destinations) or "not specified"
        pref_summary = (
            f"{profile_str}"
            f"Destinations: {dest_names}. "
            f"Theme/interests: {preferences.trip_theme or 'general'}. "
            f"Budget: {preferences.budget_level}. "
            f"Pace: {preferences.travel_pace}. "
            f"Group: {preferences.travel_group_type} of {preferences.group_size}. "
            f"Origin: {preferences.origin_country or 'not specified'}."
        )

        if not description:
            # No NL text — generate a minimal outline from preferences alone so
            # downstream steps still have an outline to reference.
            description = (
                f"A {preferences.travel_pace}-paced, {preferences.budget_level}-budget "
                f"{preferences.trip_theme or 'general'} trip to {dest_names} "
                f"for {preferences.travel_group_type} (group of {preferences.group_size})."
            )

        self.state.agent_thoughts.append(
            "🗺️ Trip Interpreter: Understanding your trip and building a detailed outline…"
        )
        broadcast({
            "type": "flow_state_update",
            "session_id": self.state.session_id,
            "data": {
                "session_id": self.state.session_id,
                "ui_status": "researching",
                "current_step": "interpreting_trip",
                "message": "Interpreting your trip description…",
            },
            "timestamp": datetime.utcnow().isoformat(),
        })

        def _task_cb(task_output):
            broadcast({
                "type": "task_complete",
                "session_id": self.state.session_id,
                "data": {
                    "agent": getattr(task_output, "agent", ""),
                    "task": (getattr(task_output, "summary", None) or "")[:100],
                },
                "timestamp": datetime.utcnow().isoformat(),
            })

        result = TravelCrews.trip_outline_crew(
            description=description,
            pref_summary=pref_summary,
            task_callback=_task_cb,
        ).kickoff()

        outline = str(result.raw if hasattr(result, "raw") else result)
        self.state.trip_outline = outline
        self.state.agent_outputs["trip_outline"] = outline
        self.state.current_step = "analyzing_dates"
        self.state.agent_thoughts.append(
            "✅ Trip Interpreter: Outline ready — handing off to date scouts and destination researchers."
        )
        logger.info("Trip outline produced for session %s", self.state.session_id)

    @listen(interpret_trip)
    def analyze_travel_dates(self) -> dict:
        """Step 1: DateScout runs in parallel for every destination, then
        overlapping windows are intersected to find dates that suit ALL locations.
        Skipped when the user already supplied confirmed exact dates.
        """
        # If the user already provided confirmed dates, skip the DateScout agent
        if self.state.confirmed_dates:
            self.state.agent_thoughts.append(
                "📅 Exact dates supplied — skipping date analysis"
            )
            logger.info("Confirmed dates already set by user; skipping DateScout")
            return {"analysis": "User-supplied confirmed dates", "is_rough": False}

        preferences = self.state.preferences
        destinations = self.state.destinations
        n = len(destinations)

        # ── Build shared context strings ─────────────────────────────────────
        rd = self.state.rough_dates
        date_parts: list[str] = []
        if rd.earliest_possible and rd.latest_possible:
            date_parts.append(
                f"exact window {rd.earliest_possible.strftime('%Y-%m-%d')} "
                f"to {rd.latest_possible.strftime('%Y-%m-%d')}"
            )
        elif rd.earliest_possible:
            date_parts.append(f"earliest date {rd.earliest_possible.strftime('%Y-%m-%d')}")
        elif rd.latest_possible:
            date_parts.append(f"latest date {rd.latest_possible.strftime('%Y-%m-%d')}")
        if rd.rough_season:
            date_parts.append(f"season: {rd.rough_season}")
        if rd.rough_duration:
            date_parts.append(f"duration: {rd.rough_duration}")
        date_ctx = ", ".join(date_parts) if date_parts else "dates not specified"

        # Rough = user has no exact departure/return window (season or duration only)
        is_rough = not (rd.earliest_possible and rd.latest_possible)

        # Parse requested trip duration so suggestions match what the user asked for
        requested_days: Optional[int] = _parse_duration_days(rd.rough_duration) if rd.rough_duration else None

        pref_context = (
            f"Travel preferences: {preferences.trip_theme or 'general'} theme, "
            f"{preferences.budget_level} budget, {preferences.travel_pace} pace, "
            f"traveling as {preferences.travel_group_type} (group of {preferences.group_size}). "
            f"Origin country: {preferences.origin_country or 'not specified'}. "
            f"Pass origin_country='{preferences.origin_country}' and "
            f"group_size={preferences.group_size} to get_flight_availability."
        )
        if self.state.trip_description:
            pref_context = (
                f"Traveller's own words: \"{self.state.trip_description}\"\n"
                + pref_context
            )
        if self.state.user_name or self.state.user_age:
            profile_line = "Traveller profile: "
            if self.state.user_name:
                profile_line += self.state.user_name
            if self.state.user_age:
                profile_line += f", age {self.state.user_age}"
            pref_context = profile_line + ". " + pref_context

        # Inject the structured trip outline produced by interpret_trip so date
        # scouts have full context about the trip's vibe and ideal date constraints.
        if self.state.trip_outline:
            pref_context = (
                f"=== Trip Outline (use to choose ideal date windows) ===\n"
                f"{self.state.trip_outline}\n"
                f"=== End of Trip Outline ===\n\n"
                + pref_context
            )

        duration_constraint = (
            f"Each option MUST span EXACTLY {requested_days} days "
            f"(the user's requested trip duration). "
        ) if requested_days else ""

        is_rough_instruction = (
            "IMPORTANT: The user has NOT specified exact travel dates — only rough "
            "seasonal or duration hints. After researching the destination's weather and "
            "upcoming events, you MUST return EXACTLY 3–4 concrete date range options. "
            f"{duration_constraint}"
            "Use THIS exact format for every option:\n"
            "Option 1: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
            "Option 2: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
            "Option 3: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
            "Option 4: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
            "Ground every option in the real weather and event data you retrieved. "
            "All proposed dates must be in the future."
        ) if is_rough else ""

        # ── Build inputs array — one dict per destination ────────────────────
        inputs_array = [
            {
                "destination_name": dest.name,
                "date_ctx": date_ctx,
                "pref_context": pref_context,
                "is_rough_instruction": is_rough_instruction,
            }
            for dest in destinations
        ]

        dest_names_str = ", ".join(d.name for d in destinations) or "not specified yet"
        self.state.agent_thoughts.append(
            f"🤖 Date Scout: Analysing dates for {n} destination"
            f"{'s' if n != 1 else ''} in parallel ({dest_names_str})…"
        )

        # ── Run date scouting in parallel (one Crew instance per destination) ───
        # Individual Crew instances are used rather than kickoff_for_each_async on
        # a single shared crew so that after execution each crew.tasks list has its
        # .output attributes populated.  The synthesis crew then receives those task
        # objects via Task.context — CrewAI injects their outputs automatically.
        def _task_cb(task_output):
            broadcast({
                "type": "task_complete",
                "session_id": self.state.session_id,
                "data": {
                    "agent": getattr(task_output, "agent", ""),
                    "task": (getattr(task_output, "summary", None) or "")[:100],
                },
                "timestamp": datetime.utcnow().isoformat(),
            })
        scouting_crews = [TravelCrews.date_scouting_crew(task_callback=_task_cb) for _ in inputs_array]

        async def _scout_all():
            return await asyncio.gather(*[
                asyncio.to_thread(crew.kickoff, inputs=inp)
                for crew, inp in zip(scouting_crews, inputs_array)
            ])

        date_crew_results = asyncio.run(_scout_all())
        async_results = [str(r.raw if hasattr(r, 'raw') else r) for r in date_crew_results]

        # ── Collect per-destination options ──────────────────────────────────
        per_dest_options: dict = {}  # dest_name → List[dict with start/end/days/rationale]
        per_dest_raw: dict = {}      # dest_name → raw agent output string

        for dest, result in zip(destinations, async_results):
            raw = str(result)
            per_dest_raw[dest.name] = raw
            if is_rough:
                opts = _parse_date_options_with_rationale(raw)
                per_dest_options[dest.name] = opts
                if opts:
                    best = opts[0]
                    self.state.agent_thoughts.append(
                        f"📅 {dest.name}: best window "
                        f"{best['start']} → {best['end']} ({best['duration_days']} days)"
                    )
                else:
                    self.state.agent_thoughts.append(
                        f"📅 {dest.name}: date analysis complete (no structured options parsed)"
                    )
            else:
                # Exact dates — just confirm they work for this destination
                parsed = _parse_dates_from_text(raw)
                if parsed:
                    per_dest_options[dest.name] = [{
                        "start": parsed.start_date.strftime("%Y-%m-%d"),
                        "end":   parsed.end_date.strftime("%Y-%m-%d"),
                        "duration_days": parsed.duration_days,
                        "rationale": f"Confirmed window for {dest.name}",
                    }]
                    self.state.agent_thoughts.append(
                        f"📅 {dest.name}: confirmed "
                        f"{parsed.start_date.date()} → {parsed.end_date.date()}"
                    )

        # ── Synthesise: dedicated LLM crew combines all results into 4 options ─
        dest_name_list = [d.name for d in destinations]

        if is_rough and per_dest_raw:
            self.state.agent_thoughts.append(
                f"🤖 Date Synthesizer: combining results for {', '.join(dest_name_list)}…"
            )
            # Pass the executed scouting crews directly — the synthesis crew wires
            # their task outputs as Task.context so no manual string-building needed.
            synthesis_raw = str(
                TravelCrews.date_synthesis_crew(
                    scouting_crews,
                    dest_names=dest_name_list,
                    pref_context=pref_context,
                    requested_days=requested_days,
                    task_callback=_task_cb,
                ).kickoff()
            )
            self.state.agent_outputs["date_synthesis"] = synthesis_raw

            # Parse the synthesis crew output → structured options
            merged_options = _parse_date_options_with_rationale(synthesis_raw)

            # Enforce requested duration on any option the LLM got wrong
            if requested_days and merged_options:
                for opt in merged_options:
                    if opt["duration_days"] != requested_days:
                        try:
                            end = datetime.fromisoformat(opt["start"]) + timedelta(days=requested_days)
                            opt["end"] = end.strftime("%Y-%m-%d")
                            opt["duration_days"] = requested_days
                        except Exception:
                            pass

            # Fallback: pure-Python window intersection if the LLM produced nothing
            if not merged_options:
                logger.warning("Date synthesis produced no structured options; falling back to window intersection")
                merged_options = _find_cross_destination_windows(
                    per_dest_options, requested_days=requested_days
                )

            analysis = _build_cross_destination_analysis(merged_options, dest_name_list)

            if merged_options:
                cr_options: List[ConfirmedDateRange] = []
                for opt in merged_options:
                    try:
                        cr_options.append(ConfirmedDateRange(
                            start_date=datetime.fromisoformat(opt["start"]),
                            end_date=datetime.fromisoformat(opt["end"]),
                            duration_days=opt["duration_days"],
                        ))
                    except Exception:
                        continue
                self.state.proposed_date_options = cr_options
                self.state.confirmed_dates = cr_options[0]
                self.state.agent_outputs["date_options"] = json.dumps(merged_options)
                best = merged_options[0]
                n_found = len(merged_options)
                label = (
                    f"across all {n} destinations" if n > 1 else dest_name_list[0]
                )
                self.state.agent_thoughts.append(
                    f"📅 {n_found} combined window(s) covering {label}. "
                    f"Best: {best['start']} → {best['end']} ({best['duration_days']} days)"
                )
        else:
            # Exact dates: use per-destination confirmation or fall back to parse
            combined_raw = "\n\n".join(per_dest_raw.values())
            analysis = combined_raw
            parsed = _parse_dates_from_text(combined_raw)
            if parsed:
                self.state.confirmed_dates = parsed
                self.state.agent_thoughts.append(
                    f"📅 Suggested dates: {parsed.start_date.date()} → {parsed.end_date.date()} "
                    f"({parsed.duration_days} days)"
                )

        combined_raw_all = "\n\n---\n\n".join(
            f"## {name}\n{raw}" for name, raw in per_dest_raw.items()
        )
        self.state.agent_outputs["date_analysis"] = combined_raw_all
        logger.info("Date analysis complete for %d destination(s)", n)

        return {"analysis": analysis, "is_rough": is_rough}

    @human_feedback(
        message="Review the suggested travel dates. Approve or request different dates?",
        emit=["dates_confirmed", "dates_rejected"],
        llm=_FEEDBACK_LLM,
        default_outcome="dates_confirmed",
    )
    @listen(analyze_travel_dates)
    def check_date_confirmation(self, date_analysis: dict):
        """Step 1b: Present suggested dates to user for confirmation before research begins"""
        dates = self.state.confirmed_dates
        self.state.current_step = "dates_proposed"
        self.state.ui_status = "awaiting_date_confirmation"
        self.state.agent_thoughts.append(
            "🕒 Waiting for date confirmation before starting destination research…"
        )
        is_rough = date_analysis.get("is_rough", False)

        # Use the pre-built structured options stored by analyze_travel_dates.
        # This avoids fragile text re-parsing and guarantees all destinations'
        # merged windows (with rationale) reach the frontend intact.
        if is_rough and self.state.agent_outputs.get("date_options"):
            try:
                proposed_options = json.loads(self.state.agent_outputs["date_options"])
            except Exception:
                proposed_options = _parse_date_options_with_rationale(
                    date_analysis.get("analysis", "")
                )
        elif is_rough:
            proposed_options = _parse_date_options_with_rationale(
                date_analysis.get("analysis", "")
            )
        else:
            proposed_options = []

        dest_names = [d.name for d in self.state.destinations]
        payload = {
            "proposed_start": dates.start_date.isoformat() if dates else None,
            "proposed_end": dates.end_date.isoformat() if dates else None,
            "duration_days": dates.duration_days if dates else None,
            "date_analysis_summary": date_analysis.get("analysis", "")[:500],
            "is_rough": is_rough,
            "destinations": dest_names,
            "proposed_options": proposed_options,  # up to 4 cross-destination windows
        }
        # Notify the frontend so it can render the confirmation UI
        broadcast({
            "type": "human_feedback_requested",
            "session_id": self.state.session_id,
            "data": {
                "step": "date_confirmation",
                "message": "Review the suggested travel dates. Approve or request different dates?",
                "options": ["dates_confirmed", "dates_rejected"],
                "session_id": self.state.session_id,
                **payload,
            },
            "timestamp": datetime.utcnow().isoformat(),
        })
        broadcast({
            "type": "flow_state_update",
            "session_id": self.state.session_id,
            "ui_status": "awaiting_date_confirmation",
            "current_step": "dates_proposed",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return payload

    @listen("dates_confirmed")
    def research_destinations(self) -> dict:
        """Step 2: DestExpert researches every destination in parallel via akickoff_for_each."""
        preferences = self.state.preferences
        destinations = self.state.destinations
        n = len(destinations)

        # Shared preferences string injected into every per-destination task
        pref_context = (
            f"Preferences: {preferences.trip_theme or 'general'} theme, "
            f"{preferences.budget_level} budget, {preferences.travel_pace} pace, "
            f"group type: {preferences.travel_group_type}, group size: {preferences.group_size}. "
            f"Origin country: {preferences.origin_country or 'not specified'}. "
            f"Always pass origin_country='{preferences.origin_country}' to get_visa_requirements "
            f"and research_destination, and group_size={preferences.group_size} to "
            f"find_accommodations. Provide recommendations that match all these preferences."
        )
        if self.state.trip_description:
            pref_context = (
                f"Traveller's own words: \"{self.state.trip_description}\"\n"
                + pref_context
            )
        if self.state.user_name or self.state.user_age:
            profile_line = "Traveller profile: "
            if self.state.user_name:
                profile_line += self.state.user_name
            if self.state.user_age:
                profile_line += f", age {self.state.user_age}"
            pref_context = profile_line + ". " + pref_context

        # Inject the structured trip outline so the destination researcher has full context.
        if self.state.trip_outline:
            pref_context = (
                f"=== Trip Outline ===\n"
                f"{self.state.trip_outline}\n"
                f"=== End of Trip Outline ===\n\n"
                + pref_context
            )

        # One inputs-dict per destination — akickoff_for_each interpolates these
        # into the {destination_name} / {pref_context} placeholders in the task.
        inputs_array = [
            {"destination_name": dest.name, "pref_context": pref_context}
            for dest in destinations
        ]

        self.state.agent_thoughts.append(
            f"🤖 Destination Expert: Researching {n} destination{'s' if n != 1 else ''} in parallel…"
        )
        broadcast({
            "type": "flow_state_update",
            "session_id": self.state.session_id,
            "data": {"session_id": self.state.session_id,
                     "message": f"Researching {n} destination(s) in parallel…"},
            "timestamp": datetime.utcnow().isoformat(),
        })

        # kickoff_for_each_async runs all N destination crews in parallel via
        # asyncio.create_task + asyncio.gather, each offloaded to a thread.
        def _task_cb(task_output):
            broadcast({
                "type": "task_complete",
                "session_id": self.state.session_id,
                "data": {
                    "agent": getattr(task_output, "agent", ""),
                    "task": (getattr(task_output, "summary", None) or "")[:100],
                },
                "timestamp": datetime.utcnow().isoformat(),
            })
        dest_crew_results = asyncio.run(
            TravelCrews.destination_research_crew(task_callback=_task_cb).kickoff_for_each_async(inputs=inputs_array)
        )
        async_results = [str(r.raw if hasattr(r, 'raw') else r) for r in dest_crew_results]

        # Combine per-destination results into one research document
        sections: List[str] = []
        for dest, result in zip(destinations, async_results):
            self.state.agent_thoughts.append(
                f"✅ Destination Expert: {dest.name} — research complete"
            )
            sections.append(f"## {dest.name}\n\n{result}")

        combined = "\n\n---\n\n".join(sections)
        logger.info("Destination research complete for %d destination(s)", n)
        self.state.agent_outputs["destination_research"] = combined

        return {"research": combined}

    @listen(research_destinations)
    def plan_logistics(self, destination_research: dict) -> dict:
        """Step 3: LogisticsManager creates itinerary and logistics plan"""
        self.state.agent_thoughts.append(
            "🤖 Logistics Manager: Planning transportation, accommodations, and daily itineraries"
        )

        preferences = self.state.preferences
        dest_list = self.state.destinations
        destinations_str = ", ".join([d.name for d in dest_list])

        dates = self.state.confirmed_dates
        if dates:
            total_days = dates.duration_days
            date_range_str = (
                f"{dates.start_date.strftime('%B %d, %Y')} to "
                f"{dates.end_date.strftime('%B %d, %Y')} ({total_days} days)"
            )
        else:
            total_days = None
            date_range_str = self.state.rough_dates.rough_duration or "flexible duration"

        # Build per-destination day schedule so the agent plans ALL destinations
        if total_days and len(dest_list) > 1:
            days_each = total_days // len(dest_list)
            remainder = total_days % len(dest_list)
            schedule_lines: List[str] = []
            day = 1
            for i, dest in enumerate(dest_list):
                n = days_each + (1 if i < remainder else 0)
                schedule_lines.append(f"Days {day}–{day + n - 1}: {dest.name} ({n} days)")
                day += n
            dest_schedule = "\n".join(schedule_lines)
        else:
            dest_schedule = ""

        trip_details = (
            f"Trip to {destinations_str} from {date_range_str}. "
            f"Budget: {preferences.budget_level}, "
            f"Pace: {preferences.travel_pace}, "
            f"Theme: {preferences.trip_theme or 'general exploration'}, "
            f"Group: {preferences.travel_group_type} ({preferences.group_size} traveler(s)), "
            f"Origin country: {preferences.origin_country or 'not specified'}."
        )
        if self.state.user_name or self.state.user_age:
            profile_parts = []
            if self.state.user_name:
                profile_parts.append(self.state.user_name)
            if self.state.user_age:
                profile_parts.append(f"age {self.state.user_age}")
            trip_details = f"Traveller: {', '.join(profile_parts)}. " + trip_details
        if self.state.trip_description:
            trip_details += (
                f"\n\nTraveller's own description: \"{self.state.trip_description}\""
                f"\nUse this to understand the spirit and vibe of the trip when crafting the itinerary."
            )
        if self.state.trip_outline:
            trip_details += (
                f"\n\n=== Pre-built Trip Outline (follow this closely) ===\n"
                f"{self.state.trip_outline}\n"
                f"=== End of Trip Outline ==="
            )
        if dest_schedule:
            trip_details += f"\n\nDestination schedule (plan days in this order):\n{dest_schedule}"
        trip_details += (
            f"\n\nAlways pass origin_country='{preferences.origin_country}' to plan_transportation "
            f"and check_travel_insurance, and group_size={preferences.group_size} to "
            f"estimate_budget_breakdown. Plan accommodations, transportation, activities, and a "
            f"day-by-day itinerary that matches these preferences and the confirmed date range."
        )

        def _task_cb(task_output):
            broadcast({
                "type": "task_complete",
                "session_id": self.state.session_id,
                "data": {
                    "agent": getattr(task_output, "agent", ""),
                    "task": (getattr(task_output, "summary", None) or "")[:100],
                },
                "timestamp": datetime.utcnow().isoformat(),
            })
        result = TravelCrews.logistics_crew(trip_details, task_callback=_task_cb).kickoff()

        self.state.agent_thoughts.append("✅ Logistics Manager: Created comprehensive itinerary")
        logger.info(f"Logistics planning complete: {result}")
        self.state.agent_outputs["logistics_plan"] = str(result)

        return {"logistics": str(result)}

    @listen(plan_logistics)
    def compile_itinerary(self, logistics_plan: dict) -> None:
        """Step 4: Compile final itinerary from actual agent outputs"""
        dates = self.state.confirmed_dates
        if dates:
            start_date = dates.start_date
            num_days = dates.duration_days
        else:
            # Only true fallback: no dates were ever resolved
            start_date = datetime.utcnow()
            num_days = 7
            logger.warning("No confirmed dates found; using today as fallback start date")

        dest_list = self.state.destinations
        destinations_str = ", ".join([d.name for d in dest_list])
        dest_names_lower = {d.name.lower(): d.name for d in dest_list}

        # Which destination does day N belong to — even split across destinations
        def _dest_for_day(day_num: int) -> str:
            if not dest_list:
                return "Destination"
            if len(dest_list) == 1 or num_days == 0:
                return dest_list[0].name
            days_each = num_days // len(dest_list)
            remainder = num_days % len(dest_list)
            day = 1
            for i, d in enumerate(dest_list):
                n = days_each + (1 if i < remainder else 0)
                if day_num <= day + n - 1:
                    return d.name
                day += n
            return dest_list[-1].name

        logistics_text = self.state.agent_outputs.get("logistics_plan", "")
        destination_text = self.state.agent_outputs.get("destination_research", "")

        # ── Parse day-by-day sections from logistics output ───────────
        day_sections: dict = {}
        day_dest_map: dict = {}  # day_num → destination name (parsed from heading)
        day_block_pattern = re.compile(
            r'(?:#{1,3}\s*)?(?:\*{0,2})Day\s+(\d+)(?:\*{0,2})\s*[—\-–]?\s*([^\n]*)\n(.*?)'
            r'(?=(?:#{1,3}\s*)?(?:\*{0,2})?Day\s+\d+|$)',
            re.IGNORECASE | re.DOTALL,
        )
        for match in day_block_pattern.finditer(logistics_text):
            day_num = int(match.group(1))
            day_title = match.group(2).strip()
            activities = _extract_activities(match.group(3).strip())
            if activities:
                day_sections[day_num] = activities
            # Check if a destination name appears in the day heading
            for name_lower, name in dest_names_lower.items():
                if name_lower in day_title.lower():
                    day_dest_map[day_num] = name
                    break

        # ── Build ItineraryDay objects ─────────────────────────────────
        itinerary_days = []
        for i in range(num_days):
            day_num = i + 1
            day_date = start_date + timedelta(days=i)
            day_dest = day_dest_map.get(day_num, _dest_for_day(day_num))
            activities = day_sections.get(day_num)
            if not activities:
                # Distribute the full logistics text evenly across days as fallback
                chunk_size = max(1, len(logistics_text) // num_days)
                chunk = logistics_text[i * chunk_size: (i + 1) * chunk_size].strip()
                activities = _extract_activities(chunk) or [f"Explore {day_dest}"]
            itinerary_days.append(ItineraryDay(
                day_number=day_num,
                date=day_date,
                title=f"Day {day_num} \u2014 {day_dest}",
                activities=activities,
                notes=destination_text[:300] if i == 0 and destination_text else None,
            ))

        # ── Extract budget estimate ────────────────────────────────────
        budget_match = re.search(r'\$[\d,]+(?:\s*[-\u2013]\s*\$[\d,]+)?', logistics_text)
        estimated_budget = budget_match.group(0) if budget_match else None

        # ── Extract key logistics lines ────────────────────────────────
        key_logistics = []
        for line in logistics_text.splitlines():
            line = line.strip().lstrip("-•*# ")
            if line and len(line) < 200 and any(
                kw in line.lower()
                for kw in ("visa", "flight", "insurance", "passport", "hotel", "accommodation", "transport")
            ):
                key_logistics.append(line)
        key_logistics = key_logistics[:8]

        self.state.itinerary = Itinerary(
            trip_title=f"Trip to {destinations_str}",
            destinations=self.state.destinations,
            date_range=self.state.confirmed_dates or ConfirmedDateRange(
                start_date=start_date,
                end_date=start_date + timedelta(days=num_days),
                duration_days=num_days,
            ),
            days=itinerary_days,
            summary=logistics_text[:600] if logistics_text else f"A carefully planned trip to {destinations_str}",
            estimated_budget=estimated_budget,
            key_logistics=key_logistics,
        )

        self.state.ui_status = "awaiting_user"
        self.state.current_step = "itinerary_ready"
        logger.info("Itinerary compiled from agent outputs")
        # Push itinerary to the frontend so it can be previewed during confirmation
        broadcast({
            "type": "itinerary_ready",
            "session_id": self.state.session_id,
            "itinerary": self.state.itinerary.model_dump(mode="json") if self.state.itinerary else None,
            "timestamp": datetime.utcnow().isoformat(),
        })

    @human_feedback(
        message="Review the itinerary. Approve or request changes?",
        emit=["finalize", "needs_revision"],
        llm=_FEEDBACK_LLM,
        default_outcome="finalize",
    )
    @listen(or_(compile_itinerary, "needs_revision"))
    def check_user_confirmation(self):
        """Step 5: Await human review of the compiled itinerary"""
        itinerary = self.state.itinerary
        self.state.ui_status = "awaiting_itinerary_confirmation"
        self.state.current_step = "itinerary_review"
        broadcast({
            "type": "human_feedback_requested",
            "session_id": self.state.session_id,
            "data": {
                "step": "itinerary_review",
                "message": "Review the itinerary. Approve or request changes?",
                "options": ["finalize", "needs_revision"],
                "session_id": self.state.session_id,
                "trip_title": itinerary.trip_title if itinerary else "Your Trip",
                "summary": itinerary.summary[:300] if itinerary else "",
                "days": len(itinerary.days) if itinerary else 0,
                "estimated_budget": itinerary.estimated_budget if itinerary else None,
            },
            "timestamp": datetime.utcnow().isoformat(),
        })
        broadcast({
            "type": "flow_state_update",
            "session_id": self.state.session_id,
            "ui_status": "awaiting_itinerary_confirmation",
            "current_step": "itinerary_review",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return self.state.itinerary

    @listen("finalize")
    def finalize_trip(self) -> None:
        """Step 6: Mark trip as finalized after user approval"""
        self.state.ui_status = "complete"
        self.state.current_step = "finalized"
        logger.info(f"Trip finalized for session {self.state.session_id}")
        broadcast({
            "type": "flow_state_update",
            "session_id": self.state.session_id,
            "ui_status": "complete",
            "current_step": "finalized",
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_state(self) -> TravelState:
        """Return current travel state"""
        return self.state

    def get_thoughts(self) -> list:
        """Return agent thoughts for frontend streaming"""
        return self.state.agent_thoughts

    def add_thought(self, thought: str) -> None:
        """Add a thought to the stream"""
        self.state.agent_thoughts.append(thought)
        self.state.updated_at = datetime.utcnow()


async def create_travel_planner_flow(
    travel_state: TravelState, callback_handler=None
) -> TravelPlannerFlow:
    """Factory function to create a configured flow with pre-populated state."""
    return TravelPlannerFlow(initial_state=travel_state)
