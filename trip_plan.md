# Trippy — CrewAI Flow Architecture

> **Stack:** FastAPI · CrewAI 1.11.0 Flows · Ollama · WebSocket · React / Vite / TypeScript / Tailwind

---

## Table of Contents

1. [High-Level Overview](#1-high-level-overview)
2. [State Machine](#2-state-machine)
3. [Flow Diagram](#3-flow-diagram)
4. [Step-by-Step Walkthrough](#4-step-by-step-walkthrough)
5. [Crew Architecture](#5-crew-architecture)
6. [Multi-Destination Parallelism](#6-multi-destination-parallelism)
7. [Human Feedback System](#7-human-feedback-system)
8. [Date Analysis Pipeline](#8-date-analysis-pipeline)
9. [Stop & Retry](#9-stop--retry)
10. [Real-Time Event Pipeline](#10-real-time-event-pipeline)
11. [Data Model — TravelState](#11-data-model--travelstate)
12. [API Reference](#12-api-reference)
13. [Key Design Decisions](#13-key-design-decisions)

---

## 1. High-Level Overview

```
Browser (React / TypeScript)
    │  POST /api/events/kickoff       ──►  FastAPI (main.py)
    │  POST /api/plan/{id}/feedback   ──►       │
    │  POST /api/plan/{id}/stop       ──►       │
    │  WS   /ws/events  ◄── all events ─────────┤
    │                                           ▼
    │                               Background daemon thread
    │                               TravelPlannerFlow.kickoff()
    │                                           │
    │                              CrewAI Flow State Machine
    │                      8 steps · 5 Crews · 2 human checkpoints
    │                      multi-destination parallel execution
```

The backend runs a **CrewAI `Flow`** in a **background daemon thread** so FastAPI's asyncio event loop is never blocked. All progress — agent thoughts, tool calls, state changes, human checkpoints — streams to the browser over a shared **WebSocket** at `/ws/events`.

---

## 2. State Machine

`TravelState` (a `FlowState` subclass) carries all data and drives the frontend status indicator via `ui_status`.

| `ui_status` | Meaning |
|---|---|
| `pending` | Session created, flow not yet started |
| `researching` | Flow is actively running crews |
| `awaiting_date_confirmation` | Blocked — waiting for human date selection / approval |
| `awaiting_itinerary_confirmation` | Blocked — waiting for human itinerary review |
| `awaiting_user` | Itinerary compiled, ready to display |
| `finalizing` | Flow progressing to completion |
| `complete` | Trip plan finalized |
| `stopping` | Stop was requested, thread draining |
| `stopped` | Flow halted by user before completion |
| `error` | Unrecoverable error |

---

## 3. Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           TravelPlannerFlow                              │
│                                                                          │
│  ┌──────────────────┐                                                    │
│  │  @start()        │  ui_status = "researching"                         │
│  │ initialize_flow  │  current_step = "interpreting_trip"                │
│  └────────┬─────────┘                                                    │
│           │ @listen(initialize_flow)                                     │
│           ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  interpret_trip                                              │        │
│  │                                                              │        │
│  │  trip_description provided?                                  │        │
│  │    YES ──► TripInterpreter Agent (no tools, standard LLM)    │        │
│  │            Input: trip_description + preferences + profile   │        │
│  │            Output: 5-section structured outline              │        │
│  │    NO  ──► auto-generate minimal outline from preferences    │        │
│  │                                                              │        │
│  │  → state.trip_outline                                        │        │
│  │  → state.agent_outputs["trip_outline"]                       │        │
│  │  (outline injected into every downstream step's context)     │        │
│  └────────────────────────┬─────────────────────────────────────┘        │
│           │ @listen(interpret_trip)                                       │
│           ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  analyze_travel_dates                                        │        │
│  │                                                              │        │
│  │  confirmed_dates already set?                                │        │
│  │    YES ──► skip all crews, return immediately                │        │
│  │    NO  ──►                                                   │        │
│  │      For each destination (in PARALLEL):                     │        │
│  │        date_scouting_crew.kickoff_for_each_async()           │        │
│  │          Date Scout Agent (max_iter=1):                      │        │
│  │          ├─ analyze_fuzzy_dates                              │        │
│  │          ├─ check_travel_seasons                             │        │
│  │          └─ get_flight_availability                          │        │
│  │                                                              │        │
│  │      Rough dates?                                            │        │
│  │        → parse per-destination Option N: blocks             │        │
│  │        → date_synthesis_crew.kickoff()                       │        │
│  │            Date Synthesizer (no tools, max_iter=1):          │        │
│  │            combines all reports → 4 cross-dest windows       │        │
│  │        → _find_cross_destination_windows() fallback          │        │
│  │          (window intersection + sliding-window generator)    │        │
│  │      Exact dates?                                            │        │
│  │        → parse per-destination ConfirmedDateRange            │        │
│  │                                                              │        │
│  │  state.proposed_date_options = [up to 4 ConfirmedDateRange] │        │
│  │  state.confirmed_dates       = options[0]  (default)         │        │
│  └────────────────────────┬─────────────────────────────────────┘        │
│           │                                                               │
│           │ @listen(analyze_travel_dates)                                 │
│           │ @human_feedback(emit=["dates_confirmed","dates_rejected"])    │
│           ▼                                                               │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  check_date_confirmation   🛑 HUMAN CHECKPOINT 1              │        │
│  │                                                              │        │
│  │  1. ui_status = "awaiting_date_confirmation"                 │        │
│  │  2. broadcast("human_feedback_requested")  ─────────────────┼──► WS  │
│  │     data: { proposed_options[], destinations[], is_rough }   │        │
│  │  3. _request_human_feedback() override blocks thread         │        │
│  │     via wait_for_feedback(session_id, timeout=600s)          │        │
│  │                                                              │        │
│  │  POST /api/plan/{id}/feedback unblocks the queue:            │        │
│  │    selected_dates? → flow.state.confirmed_dates updated first│        │
│  │    _collapse_to_outcome() bypass (no extra LLM round-trip):  │        │
│  │      "dates_confirmed" ───────────────────────────────────┐  │        │
│  │      "dates_rejected"  (flow terminates)                  │  │        │
│  └───────────────────────────────────────────────────────────┼──┘        │
│                          @listen("dates_confirmed")           │           │
│                                                               ▼           │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  research_destinations                                       │        │
│  │                                                              │        │
│  │  For each destination (in PARALLEL):                         │        │
│  │    destination_research_crew.kickoff_for_each_async()        │        │
│  │      Destination Expert Agent (max_iter=1):                  │        │
│  │      ├─ research_destination  (theme, budget, pace, origin)  │        │
│  │      ├─ get_visa_requirements (origin_country → destination) │        │
│  │      └─ find_accommodations   (group_size, pace, budget)     │        │
│  │                                                              │        │
│  │  Sections combined: "## Dest\n\nresult\n\n---\n\n## Dest2…" │        │
│  │  → state.agent_outputs["destination_research"]               │        │
│  └────────────────────────┬─────────────────────────────────────┘        │
│           │ @listen(research_destinations)                                │
│           ▼                                                               │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  plan_logistics                                              │        │
│  │                                                              │        │
│  │  logistics_crew.kickoff()                                    │        │
│  │    Logistics Manager Agent (max_iter=1):                     │        │
│  │    ├─ plan_transportation      (origin_country, group_size)  │        │
│  │    ├─ estimate_budget_breakdown (group_size)                 │        │
│  │    ├─ create_daily_itinerary   (pace, theme, group)          │        │
│  │    └─ check_travel_insurance   (origin_country)              │        │
│  │                                                              │        │
│  │  Context includes per-destination day schedule:              │        │
│  │    "Days 1–3: Paris (3 days)\nDays 4–6: Rome (3 days)…"     │        │
│  │  → state.agent_outputs["logistics_plan"]                     │        │
│  └────────────────────────┬─────────────────────────────────────┘        │
│           │ @listen(plan_logistics)                                       │
│           ▼                                                               │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  compile_itinerary   (pure Python — no LLM)                  │        │
│  │                                                              │        │
│  │  ├─ regex "Day N — Destination" blocks → activities per day  │        │
│  │  ├─ _dest_for_day(n) assigns destination by even split       │        │
│  │  ├─ extract $ budget estimate                                │        │
│  │  ├─ keyword-scan key logistics (visa/flight/hotel/insurance) │        │
│  │  └─ build Itinerary pydantic object → state.itinerary        │        │
│  │                                                              │        │
│  │  broadcast("itinerary_ready")  ─────────────────────────────┼──► WS  │
│  └────────────────────────┬─────────────────────────────────────┘        │
│           │            ◄──── loops back on "needs_revision"               │
│           │ @listen(or_(compile_itinerary, "needs_revision"))             │
│           │ @human_feedback(emit=["finalize","needs_revision"])           │
│           ▼                                                               │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  check_user_confirmation   🛑 HUMAN CHECKPOINT 2              │        │
│  │                                                              │        │
│  │  1. ui_status = "awaiting_itinerary_confirmation"            │        │
│  │  2. broadcast("human_feedback_requested")  ─────────────────┼──► WS  │
│  │  3. wait_for_feedback() blocks thread                        │        │
│  │                                                              │        │
│  │  _collapse_to_outcome() bypass:                              │        │
│  │    "finalize"       ──────────────────────────────────────┐  │        │
│  │    "needs_revision" ──► re-triggers this step (loop)      │  │        │
│  └───────────────────────────────────────────────────────────┼──┘        │
│                              @listen("finalize")              │           │
│                                                               ▼           │
│  ┌──────────────────────────────────────────────────────────────┐        │
│  │  finalize_trip                                               │        │
│  │  ui_status = "complete"                                      │        │
│  │  broadcast("flow_state_update")  ───────────────────────────┼──► WS  │
│  └──────────────────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Step-by-Step Walkthrough

### Step 0 — Session Kickoff (`POST /api/events/kickoff`)

1. FastAPI creates a UUID `session_id` and a `TravelState` from the request body.
2. `feedback_mod.register_session(session_id)` pre-creates a `queue.Queue(maxsize=1)` **before** the thread starts — the overridden `_request_human_feedback()` needs the slot ready immediately.
3. The live `TravelPlannerFlow` is stored in `_active_flows[session_id]` (protected by `threading.Lock`) so the feedback endpoint can mutate `flow.state.confirmed_dates` before unblocking the thread.
4. A **daemon thread** spawns. Inside: `set_thread_session(session_id)` stores the ID in thread-local storage, then `flow.kickoff()` blocks synchronously until the full flow completes.
5. The thread's `finally` block calls `cleanup_session`, removes the flow from `_active_flows`, and discards the session from `_stopped_sessions`.
6. FastAPI immediately returns `{"status": "started", "session_id": "..."}` — fully non-blocking.

---

### Step 1 — `initialize_flow` (`@start`)

Sets `ui_status = "researching"` and `current_step = "interpreting_trip"`. No crew or LLM work.

---

### Step 1a — `interpret_trip` (`@listen(initialize_flow)`)

The **TripInterpreter** agent (no tools, standard-tier LLM, `max_iter=3`) reads the user's natural-language `trip_description` combined with their structured preferences and produces a 5-section trip outline:

1. **Trip Vibe & Theme** — overall feel and purpose.
2. **Destinations & Highlights** — key experiences, must-do activities, estimated days per destination.
3. **Implicit Needs** — dietary, accessibility, photography, nightlife, etc.
4. **Ideal Date Constraints** — seasons / events that would make the trip exceptional.
5. **Budget Sense-check** — realism of stated budget vs. destinations and group size.

If no `trip_description` was supplied, a minimal outline is auto-generated from structured preferences alone (no LLM call).

The outline is stored in:
- `state.trip_outline` — raw markdown text.
- `state.agent_outputs["trip_outline"]` — same text, keyed for agent output reference.

**Context injection:** This outline is prepended to the `pref_context` string passed to every downstream crew — date scouting, destination research, and logistics — ensuring all agents share a consistent understanding of the trip's vibe, priorities, and constraints.

---

### Step 1b — `analyze_travel_dates` (`@listen(interpret_trip)`)

**Short-circuit:** If `confirmed_dates` is already set (user supplied exact ISO dates), all crews are skipped.

**Parallel per-destination scouting:**

Individual `date_scouting_crew()` instances are created per destination and run concurrently via `asyncio.gather` + `asyncio.to_thread`:

```python
scouting_crews = [TravelCrews.date_scouting_crew() for _ in inputs_array]

async def _scout_all():
    return await asyncio.gather(*[
        asyncio.to_thread(crew.kickoff, inputs=inp)
        for crew, inp in zip(scouting_crews, inputs_array)
    ])

date_crew_results = asyncio.run(_scout_all())
```

Individual Crew instances (rather than `kickoff_for_each_async` on a shared crew) are used so each crew's `.tasks` list retains populated `.output` attributes after execution. The synthesis crew then receives those task objects via `Task.context` — CrewAI injects their outputs automatically.

Each element of `inputs_array` is one destination's input dict:

```python
{
  "destination_name": "Tokyo",
  "date_ctx": "season: summer, duration: 14 days",
  "pref_context": "moderate budget, solo, origin: India …",
  "is_rough_instruction": "IMPORTANT: return EXACTLY 3–4 Option N: … lines"
}
```

`kickoff_for_each_async` uses `asyncio.create_task` + `asyncio.gather` internally — all N destinations research concurrently, each in its own `asyncio.to_thread(kickoff)` call. `asyncio.run()` is safe here because the flow step runs in a background thread with no running event loop.

**Rough date synthesis:**

After all per-destination scouts finish, a second crew synthesises their reports into up to 4 cross-destination windows:

```python
TravelCrews.date_synthesis_crew(
    executed_scouting_crews=scouting_crews,
    dest_names=dest_name_list,
    pref_context=pref_context,
    requested_days=requested_days,
).kickoff()
```

The synthesis task receives the scouting outputs via CrewAI's native `Task.context` mechanism — every task from every executed scouting crew is listed as context so CrewAI injects their outputs automatically. The Date Synthesizer agent has no tools — it reasons purely over these injected reports, requested duration, and user preferences to output exactly 4 `Option N: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>` lines.

If the LLM output is unparseable, `_find_cross_destination_windows()` runs as a pure-Python fallback: it intersects the per-destination option windows, then slides `requested_days`-length windows across each overlapping region to produce 4 evenly-spaced suggestions of exactly the right duration.

Duration parsing: `_parse_duration_days("2 weeks") → 14`, `"10 days" → 10`, `"1 month" → 30`.

---

### Step 1c — `check_date_confirmation` (Human Checkpoint 1)

The step body broadcasts:

- `"human_feedback_requested"` with `proposed_options[]` (structured `{start, end, duration_days, rationale}` objects for all 4 windows), destination list, and roughness flag.
- `"flow_state_update"` to update the status indicator.

Then `_request_human_feedback()` (overridden directly on `TravelPlannerFlow` — uses `self.state.session_id`, safe from any thread) calls `wait_for_feedback(session_id)`, blocking the thread on the per-session `Queue`.

When `POST /api/plan/{id}/feedback` arrives:

1. If `selected_dates` is in the body, `_active_flows[session_id].state.confirmed_dates` is updated first.
2. `submit_feedback(session_id, text)` puts the text in the queue.
3. `_collapse_to_outcome()` (also overridden) does a fast substring match against the emit strings — no secondary LLM round-trip needed.

---

### Step 2 — `research_destinations` (`@listen("dates_confirmed")`)

```python
asyncio.run(
    TravelCrews.destination_research_crew().kickoff_for_each_async(inputs=inputs_array)
)
```

All N destinations research in parallel. Results are zipped with destination names and joined into a single markdown document with `## DestName` section headers, stored in `state.agent_outputs["destination_research"]`.

---

### Step 3 — `plan_logistics` (`@listen(research_destinations)`)

Single logistics crew invocation. The context string includes:

- Full trip details (dates, preferences, origin).
- Explicit per-destination day schedule: `"Days 1–3: Paris (3 days)\nDays 4–6: Rome (3 days)…"` — computed by an even split of `duration_days` across destinations, with the remainder distributed to early destinations.

---

### Step 4 — `compile_itinerary` (`@listen(plan_logistics)`)

**No LLM — pure Python:**

1. Regex `(?:Day\s+(\d+))(?:\s*[—\-–]?\s*([^\n]*))` splits the logistics output into day blocks.
2. `_extract_activities()` extracts bullet/numbered lines per day (max 6).
3. `_dest_for_day(n)` maps each day number to the correct destination via the same even-split formula used in Step 3.
4. Falls back to evenly chunked raw text when no structured day blocks are found.
5. Regex `\$[\d,]+` extracts the budget estimate.
6. Keyword scan (visa, flight, insurance, hotel, accommodation, transport) extracts up to 8 key logistics lines.
7. Builds a typed `Itinerary` pydantic object → `state.itinerary`.
8. Broadcasts `"itinerary_ready"` with the full serialized JSON.

---

### Step 5 — `check_user_confirmation` (Human Checkpoint 2)

Triggered by `or_(compile_itinerary, "needs_revision")` — fires on **first compile** and on every revision loop-back. Same blocking pattern as Step 1c. `"finalize"` advances; `"needs_revision"` loops back to this same step.

---

### Step 6 — `finalize_trip` (`@listen("finalize")`)

Sets `ui_status = "complete"`, broadcasts `flow_state_update`.

---

## 5. Crew Architecture

```
TravelCrews (static factory)
│
├── trip_outline_crew(description, pref_summary) → Crew
│   └── Agent:   Trip Interpreter  (max_iter=3, max_retry_limit=0, no tools)
│   └── Process: sequential
│   └── Usage:   kickoff() — called once in interpret_trip step
│
├── date_scouting_crew() → Crew
│   └── Agents:  Fuzzy Date Analyst (max_iter=5), Travel Season Analyst (max_iter=5),
│   │            Flight Scout (max_iter=5), Date Scout Manager (max_iter=10)
│   └── Tools:   analyze_fuzzy_dates, check_travel_seasons, get_flight_availability
│   └── Process: hierarchical (manager orchestrates 3 specialists)
│   └── Usage:   one instance per destination, all run concurrently via asyncio.gather
│
├── date_synthesis_crew(executed_scouting_crews, dest_names, pref_context, requested_days) → Crew
│   └── Agent:   Date Synthesizer  (max_iter=5, max_retry_limit=0, no tools)
│   └── Process: sequential
│   └── Usage:   kickoff() — called once after all scouts complete;
│                receives scouting outputs via Task.context injection
│
├── destination_research_crew() → Crew
│   └── Agent:   Destination Expert  (max_iter=5, max_retry_limit=0)
│   └── Tools:   research_destination, get_visa_requirements, find_accommodations
│   └── Process: sequential
│   └── Usage:   kickoff_for_each_async([{destination_name, pref_context}, …])
│
└── logistics_crew(context: str) → Crew
    └── Agent:   Logistics Manager  (max_iter=5, max_retry_limit=0)
    └── Tools:   plan_transportation, estimate_budget_breakdown,
    │            create_daily_itinerary, check_travel_insurance
    └── Process: sequential
    └── Usage:   kickoff() — called once with full trip context
```

All agents: `verbose = False` · `cache = True` · `respect_context_window = True`

**LLM tiers** (overridable via env vars `OLLAMA_MODEL_FAST`, `OLLAMA_MODEL`, `OLLAMA_MODEL_REASONING`):

| Tier | Default model | Used by |
|---|---|---|
| fast | `qgranite4:3b` | Fuzzy Date Analyst, Travel Season Analyst, Flight Scout |
| standard | `ministral-3:8b` | Trip Interpreter, Destination Expert, Logistics Manager |
| reasoning | same as standard | Date Synthesizer, Date Scout Manager |

### Agent Tool Reference

#### Trip Interpreter
No tools. Pure reasoning over the user's `trip_description` and preference summary. Produces a 5-section structured outline (Trip Vibe, Destinations & Highlights, Implicit Needs, Ideal Date Constraints, Budget Sense-check) that is injected into every downstream step.

#### Date Scout (Hierarchical Crew)
Three specialist agents, each with a single tool, orchestrated by a manager:

| Agent | Tool | Purpose | Required inputs |
|---|---|---|---|
| Fuzzy Date Analyst | `analyze_fuzzy_dates` | Vague dates → concrete windows | `destination`, date fields from context |
| Travel Season Analyst | `check_travel_seasons` | Weather, crowds, events | `destination`, `timeframe` |
| Flight Scout | `get_flight_availability` | Prices, routes, booking tips | `destination`, `origin_country`, `group_size`, `budget_level` |
| Date Scout Manager | — | Orchestrates above 3 + synthesises report | (no tools — pure reasoning) |

#### Date Synthesizer
No tools. Pure reasoning over combined per-destination scout reports + user preferences. Outputs exactly 4 `Option N: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>` lines.

#### Destination Expert
| Tool | Purpose | Required inputs |
|---|---|---|
| `research_destination` | Attractions, cuisine, transport, costs | `destination`, `origin_country`, `group_size`, all prefs |
| `get_visa_requirements` | Visa rules by passport | `origin_country`, `destination_country` |
| `find_accommodations` | Hotel / stay options | `destination`, `group_size`, `budget_level`, `travel_pace` |

#### Logistics Manager
| Tool | Purpose | Required inputs |
|---|---|---|
| `plan_transportation` | Flights + local transport | `origin_country`, `group_size`, all prefs |
| `estimate_budget_breakdown` | Per-day cost estimates | `destination`, `group_size`, `budget_level` |
| `create_daily_itinerary` | Activity planner (once per destination) | `destination`, `duration_days`, all prefs |
| `check_travel_insurance` | Insurance options | `destination`, `origin_country` |

### Thread-Safe Tool Instances

Each tool module (`date_tools.py`, `destination_tools.py`, `logistics_tools.py`) uses `threading.local()` instead of module-level globals for `SerperDevTool` and `ScrapeWebsiteTool`. This ensures each parallel worker thread gets its own tool instance — shared instances caused concurrent `.run()` calls to corrupt each other's internal state.

```python
_local = threading.local()

def _get_serper():
    if not hasattr(_local, "serper"):
        _local.serper = SerperDevTool(n_results=3)  # one per thread
    return _local.serper

def _get_scraper():
    if not hasattr(_local, "scraper"):
        _local.scraper = ScrapeWebsiteTool()
    return _local.scraper
```

---

## 6. Multi-Destination Parallelism

### Execution Model

```
analyze_travel_dates / research_destinations
          │
          │  asyncio.run(crew.kickoff_for_each_async(inputs))
          │
          ▼
  kickoff_for_each_async (CrewAI 1.11.0)
    ├─ asyncio.create_task( kickoff_async(crew_copy_1, input_1) )
    ├─ asyncio.create_task( kickoff_async(crew_copy_2, input_2) )
    └─ asyncio.create_task( kickoff_async(crew_copy_N, input_N) )
          │
          │  asyncio.gather(*tasks)   ← all run concurrently
          │
          ▼  each task calls:
     asyncio.to_thread(crew_copy.kickoff)
          │
          ▼
     ThreadPoolExecutor thread   ← blocking Ollama + Serper calls here
```

`asyncio.run()` is called from the flow's background thread — there is no running event loop in that thread so this is safe. Results are returned in **input order** regardless of completion order.

### Why `kickoff_for_each` Was Not Enough

`Crew.kickoff_for_each(inputs)` is a plain sequential `for` loop — it offers no parallelism. `kickoff_for_each_async` is the correct API for concurrent execution and was introduced for exactly this use case.

### Date Cross-Destination Synthesis

After all N scouts finish, their raw outputs are combined into a single synthesis context:

```
=== Date research for Paris ===
<raw scout output>

=== Date research for Tokyo ===
<raw scout output>
```

The synthesizer produces up to 4 combined windows where all destinations align (good weather, acceptable crowd levels, matching user preferences). Each option references every destination by name in its rationale.

**Fallback logic (`_find_cross_destination_windows`):**

1. Intersect per-destination option windows pairwise — keep only regions where all destinations overlap.
2. Sort overlapping regions longest-first.
3. For each region, slide N evenly-spaced `requested_days`-long windows across it.
4. If no inter-destination overlap exists, fall back to the first destination's options with duration enforced.

### Destination Day Schedule

The logistics crew receives an explicit per-destination day allocation:

```
Days 1–4:  Paris   (4 days)
Days 5–7:  Rome    (3 days)
Days 8–10: Berlin  (3 days)
```

Computed as: `days_per_dest = total_days // n_dests`, remainder distributed to early destinations. `compile_itinerary` uses the same formula via `_dest_for_day(day_num)` to assign the correct destination label to every `ItineraryDay`.

---

## 7. Human Feedback System

```
@human_feedback decorator → calls _request_human_feedback() on TravelPlannerFlow
        │
        ▼
TravelPlannerFlow._request_human_feedback()   ← overridden (uses self.state.session_id)
        │
        ▼
_feedback_mod.wait_for_feedback(session_id, timeout=600)
        │
        ▼
queue.Queue.get(timeout=600)   ← BLOCKS the flow thread

        ▲  queue.put_nowait(feedback_text)
        │
POST /api/plan/{session_id}/feedback
  {
    "feedback_text": "approve option 2",
    "selected_dates": {           ← optional; applied before unblocking
      "start_date": "2026-07-01",
      "end_date":   "2026-07-15",
      "duration_days": 14
    }
  }
        ▲
        │
  User submits HumanFeedbackCard in the React frontend
```

**`_collapse_to_outcome()` override** — bypasses the secondary LLM classification round-trip that CrewAI normally uses to map feedback text to an emit outcome. Instead, a fast exact-then-substring match against the emit strings is used (the frontend always sends the exact outcome token):

```python
def _collapse_to_outcome(self, feedback, outcomes, llm=None):
    fb = feedback.strip().lower()
    for outcome in outcomes:       # exact match first
        if outcome.lower() == fb:
            return outcome
    for outcome in outcomes:       # substring fallback
        if outcome.lower() in fb:
            return outcome
    return outcomes[0]             # default: first = approval path
```

### Feedback Module Public API (`src/feedback.py`)

| Function | Purpose |
|---|---|
| `register_session(id)` | Pre-create the queue slot — call BEFORE spawning the thread |
| `set_thread_session(id)` | Associate the current thread with a session ID |
| `submit_feedback(id, text)` | Deliver text to the waiting queue — returns True/False |
| `wait_for_feedback(id, timeout)` | Block current thread until feedback arrives |
| `has_pending_slot(id)` | True if a slot exists and is empty (waiting) |
| `cleanup_session(id)` | Remove the queue slot — call in thread's finally block |

---

## 8. Date Analysis Pipeline

```
User input (rough dates + N destinations)
        │
        ▼
date_scouting_crew.kickoff_for_each_async([dest_1, dest_2, …, dest_N])
        │  (all in parallel)
        ├─► dest_1 raw output  →  _parse_date_options_with_rationale()
        │                         per_dest_options["dest_1"] = [{start,end,days,rationale}, …]
        ├─► dest_2 raw output  →  per_dest_options["dest_2"] = […]
        └─► dest_N raw output  →  per_dest_options["dest_N"] = […]
        │
        ▼
date_synthesis_crew.kickoff(synthesis_context)
        │
        ├─ OUTPUT: up to 4  "Option N: YYYY-MM-DD to YYYY-MM-DD (N days) - rationale" lines
        │
        │  _parse_date_options_with_rationale(synthesis_raw) → merged_options[]
        │
        │  Duration enforcement:
        │    for opt in merged_options:
        │        if opt["duration_days"] != requested_days:
        │            opt["end"] = start + timedelta(days=requested_days)
        │
        ├─ FALLBACK (if synthesis output unparseable):
        │    _find_cross_destination_windows(per_dest_options, requested_days)
        │      step 1: pairwise window intersection across all destinations
        │      step 2: slide requested_days windows across each overlap region
        │
        ▼
state.proposed_date_options = [ConfirmedDateRange, …]  (up to 4)
state.confirmed_dates        = proposed_date_options[0]  (default selection)
state.agent_outputs["date_options"] = json.dumps(merged_options)
        │
        ▼
check_date_confirmation broadcasts proposed_options[]
        → HumanFeedbackCard renders up to 4 date option cards
        → user picks one → frontend POSTs selected_dates
        → feedback endpoint sets confirmed_dates on live flow.state
```

---

## 9. Stop & Retry

### Stop Flow

```
Frontend: user clicks "⛔ Stop Planning"
        │
        ▼
POST /api/plan/{session_id}/stop
        │
        ├─ _stopped_sessions.add(session_id)
        ├─ _feedback_mod.submit_feedback(session_id, "__stop__")  ← unblocks any wait
        └─ broadcast({ type: "flow_stopped", … })
        │
Background thread:
  ├─ if blocked on wait_for_feedback → queue unblocked with "__stop__"
  ├─ flow.kickoff() raises or returns
  ├─ finally: cleanup_session, _active_flows.pop, _stopped_sessions.discard
  └─ exception handler: was_stopped=True → no flow_error broadcast
        │
Frontend WS handler:
  "flow_stopped" → ui_status = "stopped", pendingFeedback = null
```

### Retry Flow

```
Frontend: user clicks "🔄 Retry"
        │
        ▼
retryFlow() hook:
  1. store.reset()                          ← clears session, thoughts, itinerary
  2. initializePlan(storeRef.current.lastPlanRequest)  ← re-submits same form data
        │
        ▼
POST /api/events/kickoff  (new session_id, same inputs)
```

The last form submission is persisted in `useTravelStore.lastPlanRequest` (set by `initializePlan` on every call, preserved through `reset()`). `retryFlow()` reads it via a ref (`storeRef.current`) to avoid stale closure issues.

### Frontend Status Driven Behavior

**Stop button visible** for statuses: `researching`, `awaiting_date_confirmation`, `awaiting_itinerary_confirmation`, `awaiting_user`

**Stop button disabled** (spinner) during: `stopping`

**Retry banner shown** for: `error`, `stopped`

---

## 10. Real-Time Event Pipeline

```
CrewAI Event Bus (module-level singleton)
        │
        │  WebSocketEventListener.setup_listeners()
        │  (auto-registered when src.listeners is imported)
        │
        ▼
broadcast(data: dict)        ← thread-safe, callable from any thread
        │
        │  worker thread? → asyncio.run_coroutine_threadsafe(_send_all, loop)
        │  event loop?    → asyncio.create_task(_send_all)
        │
        ▼
_send_all(message: str)
  for ws in connected_clients:
      await ws.send_text(message)   ← dead sockets pruned silently
```

The `_main_loop` reference is set during FastAPI lifespan startup via `set_main_loop(asyncio.get_running_loop())`.

### WS Event Types

| Type | Trigger |
|---|---|
| `crew_kickoff_started` | Crew begins execution |
| `crew_kickoff_completed` | Crew finishes successfully |
| `crew_kickoff_failed` | Crew raises an exception |
| `agent_execution_started` | Agent reasoning begins |
| `agent_execution_completed` | Agent reasoning finishes |
| `task_started` | Task execution begins |
| `task_completed` | Task finishes |
| `task_failed` | Task raises an exception |
| `tool_usage_started` | Tool call begins |
| `tool_usage_finished` | Tool call returns |
| `tool_usage_error` | Tool call fails |
| `llm_call_started` | LLM prompt sent |
| `llm_call_completed` | LLM response received |
| `llm_call_failed` | LLM call errors |
| `llm_call_chunk` | Streaming LLM token |
| `flow_method_started` | Flow step begins |
| `flow_method_finished` | Flow step completes |
| `flow_method_failed` | Flow step raises |
| `human_feedback_requested` | Human checkpoint reached — carries `proposed_options[]` |
| `flow_state_update` | `ui_status` or `current_step` changed |
| `itinerary_ready` | Full itinerary compiled (Step 4) |
| `flow_stopped` | Stop requested and acknowledged |
| `flow_error` | Unhandled exception in flow thread |

---

## 11. Data Model — TravelState

```
TravelState  (extends FlowState)
│
├── session_id: str
├── user_id: Optional[str]
├── trip_description: Optional[str]   (raw NL text from the user)
├── user_name: Optional[str]          (traveller's first name)
├── user_age: Optional[str]           (traveller's age)
│
├── rough_dates: FuzzyDateRange
│   ├── rough_season:       Optional[str]   e.g. "summer"
│   ├── rough_duration:     Optional[str]   e.g. "2 weeks"
│   ├── earliest_possible:  Optional[datetime]
│   └── latest_possible:    Optional[datetime]
│
├── destinations: List[DestinationInput]
│   └── { name: str, type: str, priority: int }
│
├── preferences: TravelPreferences
│   ├── budget_level:       "budget" | "moderate" | "luxury"
│   ├── travel_pace:        "relaxed" | "moderate" | "fast"
│   ├── trip_theme:         Optional[str]  e.g. "adventure", "cultural"
│   ├── travel_group_type:  "solo" | "couple" | "family" | "friends"
│   ├── group_size:         int
│   └── origin_country:     str  (passport / departure country)
│
├── confirmed_dates: Optional[ConfirmedDateRange]
│   ├── start_date:    datetime
│   ├── end_date:      datetime
│   └── duration_days: int
│
├── proposed_date_options: List[ConfirmedDateRange]
│   └── up to 4 cross-destination windows (rough dates only)
│
├── trip_outline: Optional[str]         (structured outline from TripInterpreter)
│
├── agent_outputs: Dict[str, str]
│   ├── "trip_outline"           ← structured 5-section trip outline
│   ├── "date_analysis"          ← combined per-destination raw scout outputs
│   ├── "date_synthesis"         ← raw date synthesis crew output
│   ├── "date_options"           ← json.dumps(merged_options list)
│   ├── "destination_research"   ← combined per-destination research markdown
│   └── "logistics_plan"         ← full logistics + day-by-day itinerary text
│
├── itinerary: Optional[Itinerary]
│   ├── trip_title:        str
│   ├── destinations:      List[DestinationInput]
│   ├── date_range:        ConfirmedDateRange
│   ├── days:              List[ItineraryDay]
│   │   └── { day_number, date, title, activities: List[str], notes }
│   ├── summary:           str
│   ├── estimated_budget:  Optional[str]
│   └── key_logistics:     List[str]
│
├── ui_status:    str   (drives frontend status indicator)
│   values: pending | researching | awaiting_date_confirmation |
│           awaiting_itinerary_confirmation | awaiting_user |
│           finalizing | complete | stopping | stopped | error
│
└── current_step: str   (drives frontend progress timeline)
```

---

## 12. API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/api/events/kickoff` | Start a new flow — returns `{ session_id }` immediately (non-blocking) |
| `WS` | `/ws/events` | Real-time CrewAI event stream (shared across all active sessions) |
| `POST` | `/api/plan/{session_id}/feedback` | Submit human feedback to unblock a waiting checkpoint |
| `POST` | `/api/plan/{session_id}/stop` | Request graceful cancellation of an in-flight flow |
| `GET` | `/api/plan/{session_id}` | Retrieve persisted session state from Redis |
| `POST` | `/api/plan/initialize` | Legacy: synchronous init with Redis — not used by the main UI |

### Kickoff Body (`POST /api/events/kickoff`)

```json
{
  "rough_dates": {
    "rough_season": "summer",
    "rough_duration": "2 weeks"
  },
  "destinations": [
    { "name": "Paris", "type": "city", "priority": 1 },
    { "name": "Rome",  "type": "city", "priority": 2 }
  ],
  "preferences": {
    "budget_level": "moderate",
    "travel_pace": "relaxed",
    "trip_theme": "cultural",
    "travel_group_type": "couple",
    "group_size": 2,
    "origin_country": "India"
  },
  "trip_description": "A romantic cultural trip through Europe with lots of food and wine",
  "user_name": "Rohit",
  "user_age": "28"
}
```

### Feedback Body (`POST /api/plan/{session_id}/feedback`)

```json
{
  "feedback_text": "dates_confirmed",
  "selected_dates": {
    "start_date":    "2026-07-01T00:00:00",
    "end_date":      "2026-07-15T00:00:00",
    "duration_days": 14
  }
}
```

`selected_dates` is optional. When present the endpoint applies it to `flow.state.confirmed_dates` **before** unblocking the queue, so the flow thread immediately has the user's chosen window available.

---

## 13. Key Design Decisions

| Decision | Rationale |
|---|---|
| **`interpret_trip` step before date scouting** | A structured TripInterpreter outline produced *first* gives every downstream agent (date scouts, destination researchers, logistics planner) a shared understanding of the trip's vibe, priorities, and implicit needs — leading to more consistent and context-aware results |
| **Trip outline context injection** | The `trip_outline` is prepended to the `pref_context` string passed to every crew, so even if different agents use different LLM tiers they all reason from the same traveller intent |
| **Background daemon thread** | `Flow.kickoff()` is synchronous and blocking; a thread keeps FastAPI's async event loop free for HTTP and WebSocket I/O |
| **Per-destination crew instances for date scouting** | Individual `date_scouting_crew()` instances (not `kickoff_for_each_async` on a shared crew) are created per destination so that each crew's `.tasks` list retains populated `.output` attributes — the synthesis crew then receives those via `Task.context` injection |
| **`threading.local()` for tool instances** | `SerperDevTool` and `ScrapeWebsiteTool` are not thread-safe for concurrent `.run()` calls; per-thread instances eliminate cross-destination result corruption |
| **Separate `date_synthesis_crew` with no-tool agent** | A pure reasoning pass over all per-destination scouting reports produces cross-destination windows that account for every location simultaneously; dedicated crew with no tools avoids unnecessary tool calls in a reasoning-only step |
| **`_find_cross_destination_windows` fallback** | Deterministic pure-Python window intersection + sliding-window generator ensures the user always gets 4 options of exactly the right duration, even when the LLM produces unparseable output |
| **`_request_human_feedback()` override on `TravelPlannerFlow`** | CrewAI's `@human_feedback` decorator calls `input()` internally; overriding the method on the Flow class uses `self.state.session_id` — always available, safe from any thread, no reliance on brittle thread-local lookup |
| **`_collapse_to_outcome()` override** | Eliminates a secondary LLM round-trip to classify feedback text; the frontend sends exact emit outcome strings so a substring match suffices |
| **`_active_flows` dict + `threading.Lock`** | Lets the HTTP feedback endpoint safely mutate `flow.state.confirmed_dates` on the live flow object before unblocking the queue — preserving the user's date selection across the async/thread boundary |
| **Stop via `submit_feedback("__stop__")`** | Reuses the existing feedback queue to unblock a waiting `@human_feedback` step without a separate signalling mechanism; `_stopped_sessions` then suppresses the spurious `flow_error` broadcast that would otherwise fire |
| **`compile_itinerary` is pure Python** | Avoids a 4th per-step LLM call; deterministic regex parsing of the structured "Day N — Dest" output from the logistics agent is fast and cheap |
| **`or_(compile_itinerary, "needs_revision")`** | Makes the revision loop explicit in the flow DAG; the human review step re-runs without re-running the expensive research or logistics phases |
| **`max_iter` tuned per agent role** | `max_iter=5` for most agents (enough for tool use + correction), `max_iter=10` for the Date Scout Manager (orchestrating 3 specialists needs more iterations), `max_iter=3` for the Trip Interpreter (pure reasoning, rarely needs retries). `max_retry_limit=0` on all tasks prevents CrewAI's internal retry machinery from stalling |
| **Per-destination day schedule in logistics context** | Explicitly telling the LogisticsManager "Days 1–3: Paris, Days 4–6: Rome" prevents it from defaulting to only the first destination in multi-destination trips |
| **`agent_outputs["date_options"]` as JSON** | Storing structured `{start, end, duration_days, rationale}` dicts avoids re-parsing text in the confirmation step and guarantees the frontend date cards reflect accurate data |
| **`lastPlanRequest` in Zustand store** | Persists the original form submission so `retryFlow()` can restart with the exact same inputs without requiring the user to re-submit the form |
