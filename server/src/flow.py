"""CrewAI Flow for Travel Planning State Machine"""

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

    @start()
    def initialize_flow(self) -> None:
        """Entry point: Validate inputs and initialize state"""
        logger.info(f"Starting travel planning for session {self.state.session_id}")
        self.state.ui_status = "researching"
        self.state.current_step = "analyzing_dates"

    @listen(initialize_flow)
    def analyze_travel_dates(self) -> dict:
        """Step 1: DateScout analyzes fuzzy dates (skipped when user supplied exact dates)"""
        # If the user already provided confirmed dates, skip the DateScout agent
        if self.state.confirmed_dates:
            self.state.agent_thoughts.append(
                "📅 Exact dates supplied — skipping date analysis"
            )
            logger.info("Confirmed dates already set by user; skipping DateScout")
            return {"analysis": "User-supplied confirmed dates"}

        self.state.agent_thoughts.append(
            "🤖 Date Scout: Analyzing your travel preferences and fuzzy dates"
        )

        preferences = self.state.preferences
        destinations_str = (
            ", ".join([d.name for d in self.state.destinations])
            if self.state.destinations
            else "not specified yet"
        )

        # Build a rich date context so the agent passes real values to the tools
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

        dates_description = (
            f"Destinations: {destinations_str}. "
            f"Date info: {date_ctx}. "
            f"Travel preferences: {preferences.trip_theme or 'general'} theme, "
            f"{preferences.budget_level} budget, {preferences.travel_pace} pace, "
            f"traveling as {preferences.travel_group_type} (group of {preferences.group_size}). "
            f"Origin country: {preferences.origin_country or 'not specified'}. "
            f"Pass all date fields (earliest_date, latest_date, rough_season, rough_duration) "
            f"to the tools so queries are anchored to the correct months. "
            f"Also pass origin_country='{preferences.origin_country}' and "
            f"group_size={preferences.group_size} to get_flight_availability."
        )

        if is_rough:
            dates_description += (
                "\n\nIMPORTANT: The user has NOT specified exact travel dates — only rough "
                "seasonal or duration hints. After researching the destination's weather and "
                "upcoming events, you MUST return EXACTLY 3–4 concrete date range options that "
                "all suit the season and location. Use THIS exact format for every option:\n"
                "Option 1: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
                "Option 2: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
                "Option 3: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
                "Option 4: YYYY-MM-DD to YYYY-MM-DD (N days) - <why this window is ideal>\n"
                "Ground every option in the real weather and event data you retrieved. "
                "All proposed dates must be in the future."
            )

        result = TravelCrews.date_scouting_crew(dates_description).kickoff()

        self.state.agent_thoughts.append(f"✅ Date Scout: {str(result)[:100]}...")
        logger.info(f"Date analysis complete: {result}")
        self.state.agent_outputs["date_analysis"] = str(result)

        if is_rough:
            # Parse all proposed date windows from the agent's output
            options = _parse_multiple_date_ranges(str(result))
            if options:
                self.state.proposed_date_options = options
                self.state.confirmed_dates = options[0]  # default to first (best) option
                self.state.agent_thoughts.append(
                    f"📅 {len(options)} date window(s) proposed. "
                    f"Best: {options[0].start_date.date()} → {options[0].end_date.date()} "
                    f"({options[0].duration_days} days)"
                )
        else:
            # Exact dates supplied: parse the single confirmed range
            parsed = _parse_dates_from_text(str(result))
            if parsed:
                self.state.confirmed_dates = parsed
                self.state.agent_thoughts.append(
                    f"📅 Suggested dates: {parsed.start_date.date()} → {parsed.end_date.date()} "
                    f"({parsed.duration_days} days)"
                )

        return {"analysis": str(result), "is_rough": is_rough}

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
        payload = {
            "proposed_start": dates.start_date.isoformat() if dates else None,
            "proposed_end": dates.end_date.isoformat() if dates else None,
            "duration_days": dates.duration_days if dates else None,
            "date_analysis_summary": date_analysis.get("analysis", "")[:300],
            "is_rough": date_analysis.get("is_rough", False),
            "proposed_options": _parse_date_options_with_rationale(
                date_analysis.get("analysis", "")
            ) if date_analysis.get("is_rough") else [],
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
        """Step 2: DestExpert researches all destinations"""
        self.state.agent_thoughts.append(
            "🤖 Destination Expert: Researching recommended destinations based on season and interests"
        )

        preferences = self.state.preferences
        destinations_str = ", ".join([d.name for d in self.state.destinations])
        research_context = (
            f"Destinations: {destinations_str}. "
            f"Preferences: {preferences.trip_theme or 'general'} theme, "
            f"{preferences.budget_level} budget, {preferences.travel_pace} pace, "
            f"group type: {preferences.travel_group_type}, group size: {preferences.group_size}. "
            f"Origin country: {preferences.origin_country or 'not specified'}. "
            f"Always pass origin_country='{preferences.origin_country}' to get_visa_requirements "
            f"and research_destination, and group_size={preferences.group_size} to "
            f"find_accommodations. Provide recommendations that match all these preferences."
        )

        result = TravelCrews.destination_research_crew(research_context).kickoff()

        self.state.agent_thoughts.append(
            f"✅ Destination Expert: Researched {len(self.state.destinations)} destinations"
        )
        logger.info(f"Destination research complete: {result}")
        self.state.agent_outputs["destination_research"] = str(result)

        return {"research": str(result)}

    @listen(research_destinations)
    def plan_logistics(self, destination_research: dict) -> dict:
        """Step 3: LogisticsManager creates itinerary and logistics plan"""
        self.state.agent_thoughts.append(
            "🤖 Logistics Manager: Planning transportation, accommodations, and daily itineraries"
        )

        preferences = self.state.preferences
        destinations = ", ".join([d.name for d in self.state.destinations])

        dates = self.state.confirmed_dates
        date_range_str = (
            f"{dates.start_date.strftime('%B %d, %Y')} to {dates.end_date.strftime('%B %d, %Y')} "
            f"({dates.duration_days} days)"
            if dates
            else self.state.rough_dates.rough_duration or "flexible duration"
        )

        trip_details = (
            f"Trip to {destinations} from {date_range_str}. "
            f"Budget: {preferences.budget_level}, "
            f"Pace: {preferences.travel_pace}, "
            f"Theme: {preferences.trip_theme or 'general exploration'}, "
            f"Group: {preferences.travel_group_type} ({preferences.group_size} traveler(s)), "
            f"Origin country: {preferences.origin_country or 'not specified'}. "
            f"Always pass origin_country='{preferences.origin_country}' to plan_transportation "
            f"and check_travel_insurance, and group_size={preferences.group_size} to "
            f"estimate_budget_breakdown. Plan accommodations, transportation, activities, and a "
            f"day-by-day itinerary that matches these preferences and the confirmed date range."
        )

        result = TravelCrews.logistics_crew(trip_details).kickoff()

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

        destination_name = self.state.destinations[0].name if self.state.destinations else "Destination"
        destinations_str = ", ".join([d.name for d in self.state.destinations])

        logistics_text = self.state.agent_outputs.get("logistics_plan", "")
        destination_text = self.state.agent_outputs.get("destination_research", "")

        # ── Parse day-by-day sections from logistics output ───────────
        day_sections: dict = {}
        day_block_pattern = re.compile(
            r'(?:#{1,3}\s*)?(?:\*{0,2})Day\s+(\d+)(?:\*{0,2})[^\n]*\n(.*?)'
            r'(?=(?:#{1,3}\s*)?(?:\*{0,2})?Day\s+\d+|$)',
            re.IGNORECASE | re.DOTALL,
        )
        for match in day_block_pattern.finditer(logistics_text):
            day_num = int(match.group(1))
            activities = _extract_activities(match.group(2).strip())
            if activities:
                day_sections[day_num] = activities

        # ── Build ItineraryDay objects ─────────────────────────────────
        itinerary_days = []
        for i in range(num_days):
            day_num = i + 1
            day_date = start_date + timedelta(days=i)
            activities = day_sections.get(day_num)
            if not activities:
                # Distribute the full logistics text evenly across days as fallback
                chunk_size = max(1, len(logistics_text) // num_days)
                chunk = logistics_text[i * chunk_size: (i + 1) * chunk_size].strip()
                activities = _extract_activities(chunk) or [f"Explore {destination_name}"]
            itinerary_days.append(ItineraryDay(
                day_number=day_num,
                date=day_date,
                title=f"Day {day_num} \u2014 {destination_name}",
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
