# Trippy — CrewAI Flow Architecture Report

> **Stack:** FastAPI · CrewAI Flows · Ollama (ministral-3:8b) · WebSocket · React/Vite/TypeScript/Tailwind

---

## Table of Contents
1. [High-Level Overview](#1-high-level-overview)
2. [State Machine](#2-state-machine)
3. [Flow Diagram](#3-flow-diagram)
4. [Step-by-Step Walkthrough](#4-step-by-step-walkthrough)
5. [Crew Architecture](#5-crew-architecture)
6. [Human Feedback System](#6-human-feedback-system)
7. [Date Option Selection](#7-date-option-selection)
8. [Real-Time Event Pipeline](#8-real-time-event-pipeline)
9. [Data Model — TravelState](#9-data-model--travelstate)
10. [API Entry Points](#10-api-entry-points)
11. [Key Design Decisions](#11-key-design-decisions)

---

## 1. High-Level Overview

```
Browser (React/TypeScript)
    │  POST /api/events/kickoff  ──►  FastAPI (main.py)
    │                                     │
    │  WS  /ws/events  ◄── events ────────┤
    │                                     │
    │  POST /api/plan/{id}/feedback ──►   │
    │                                     ▼
    │                           Background Thread
    │                           TravelPlannerFlow.kickoff()
    │                                     │
    │                          CrewAI Flow State Machine
    │                    (6 steps · 3 Crews · 2 human checkpoints)
```

The backend runs a **CrewAI `Flow`** inside a **background thread** so FastAPI's async event loop is never blocked. All progress streams to the browser over a single **WebSocket** at `/ws/events`.

---

## 2. State Machine

`TravelState` (a `FlowState` subclass) holds all data and drives the UI status indicator.

| `ui_status` value | Meaning |
|---|---|
| `pending` | Session created, flow not yet started |
| `researching` | Flow is actively running crews |
| `awaiting_date_confirmation` | Blocked — waiting for human date selection/approval |
| `awaiting_itinerary_confirmation` | Blocked — waiting for human itinerary review |
| `awaiting_user` | Itinerary compiled, ready to display |
| `complete` | Trip plan finalized |
| `error` | Unrecoverable error |

---

## 3. Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                         TravelPlannerFlow                              │
│                                                                        │
│  ┌──────────────────┐                                                  │
│  │  @start()        │                                                  │
│  │ initialize_flow  │  Sets ui_status="researching"                    │
│  └────────┬─────────┘                                                  │
│           │ @listen(initialize_flow)                                   │
│           ▼                                                            │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  analyze_travel_dates                                    │          │
│  │                                                          │          │
│  │  confirmed_dates already set?                            │          │
│  │    YES ──► skip crew, return immediately                 │          │
│  │    NO  ──► TravelCrews.date_scouting_crew().kickoff()    │          │
│  │              Date Scout Agent (max_iter=2):              │          │
│  │              ├─ analyze_fuzzy_dates                      │          │
│  │              ├─ check_travel_seasons                     │          │
│  │              └─ get_flight_availability                  │          │
│  │                                                          │          │
│  │  Rough dates? → parse 3-4 options                        │          │
│  │  Exact dates? → parse single ConfirmedDateRange          │          │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │                                                             │
│           │ @listen(analyze_travel_dates)                               │
│           │ @human_feedback(emit=["dates_confirmed","dates_rejected"])   │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  check_date_confirmation   🛑 HUMAN CHECKPOINT 1          │          │
│  │                                                          │          │
│  │  1. ui_status = "awaiting_date_confirmation"             │          │
│  │  2. broadcast("human_feedback_requested") with           │          │
│  │     proposed_options[] (if rough dates)  ──────────────►│──► WS   │
│  │  3. _request_human_feedback() override blocks thread     │          │
│  │     via wait_for_feedback(session_id)                    │          │
│  │  4. waits for POST /api/plan/{id}/feedback               │          │
│  │     (10-min timeout → default "approve")                 │          │
│  │                                                          │          │
│  │  If selected_dates in body → apply to flow.state first   │          │
│  │  Ollama classifies response text:                        │          │
│  │    "dates_confirmed" ──────────────────────────────────┐ │          │
│  │    "dates_rejected"  (flow stops)                      │ │          │
│  └────────────────────────────────────────────────────────┼─┘          │
│                         @listen("dates_confirmed")         │            │
│                                                            ▼            │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  research_destinations                                   │          │
│  │                                                          │          │
│  │  TravelCrews.destination_research_crew().kickoff()       │          │
│  │    Destination Expert Agent (max_iter=2):                │          │
│  │    ├─ research_destination (origin_country, group_size,  │          │
│  │    │    theme, budget, pace)                             │          │
│  │    ├─ get_visa_requirements (origin_country → dest)      │          │
│  │    └─ find_accommodations (group_size, pace, budget)     │          │
│  │                                                          │          │
│  │  → state.agent_outputs["destination_research"]           │          │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │ @listen(research_destinations)                              │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  plan_logistics                                          │          │
│  │                                                          │          │
│  │  TravelCrews.logistics_crew().kickoff()                  │          │
│  │    Logistics Manager Agent (max_iter=2):                 │          │
│  │    ├─ plan_transportation (origin_country, group_size)   │          │
│  │    ├─ estimate_budget_breakdown (group_size)             │          │
│  │    ├─ create_daily_itinerary (pace, theme, group)        │          │
│  │    └─ check_travel_insurance (origin_country)            │          │
│  │                                                          │          │
│  │  → state.agent_outputs["logistics_plan"]                 │          │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │ @listen(plan_logistics)                                     │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  compile_itinerary   (pure Python — no LLM)              │          │
│  │                                                          │          │
│  │  ├─ regex "Day N" blocks → activities per day            │          │
│  │  ├─ extract $ budget estimate                            │          │
│  │  ├─ extract key logistics lines (visa/flight/hotel...)   │          │
│  │  └─ build Itinerary pydantic object                      │          │
│  │                                                          │          │
│  │  broadcast("itinerary_ready")  ────────────────────────►│──► WS   │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │                             ◄──── loops back on revision   │
│           │ @listen(or_(compile_itinerary, "needs_revision"))           │
│           │ @human_feedback(emit=["finalize","needs_revision"])         │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  check_user_confirmation   🛑 HUMAN CHECKPOINT 2          │          │
│  │                                                          │          │
│  │  1. ui_status = "awaiting_itinerary_confirmation"        │          │
│  │  2. broadcast("human_feedback_requested")  ────────────►│──► WS   │
│  │  3. wait_for_feedback(session_id) blocks thread          │          │
│  │                                                          │          │
│  │  Ollama classifies response:                             │          │
│  │    "finalize"        ──────────────────────────────────┐ │          │
│  │    "needs_revision"  ──► loops back to this step       │ │          │
│  └────────────────────────────────────────────────────────┼─┘          │
│                                  @listen("finalize")       │            │
│                                                            ▼            │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  finalize_trip                                           │          │
│  │  ui_status = "complete"                                  │          │
│  │  broadcast("flow_state_update")  ──────────────────────►│──► WS   │
│  └──────────────────────────────────────────────────────────┘          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Step-by-Step Walkthrough

### Step 0 — Session Kickoff (`POST /api/events/kickoff`)

1. FastAPI creates a UUID `session_id` and a `TravelState` from the request body.
2. `feedback_mod.register_session(session_id)` pre-creates a `queue.Queue(maxsize=1)`.
3. The live `TravelPlannerFlow` instance is stored in `_active_flows[session_id]` so the feedback endpoint can mutate `flow.state` later.
4. A **daemon thread** is spawned. Inside it: `set_thread_session` stores the session ID in thread-local storage (fallback for non-flow threads), then `flow.kickoff()` is called synchronously.
5. The thread's `finally` block always calls `cleanup_session` and removes the flow from `_active_flows`.
6. FastAPI immediately returns `{"status": "started", "session_id": "..."}` — fully non-blocking.

---

### Step 1 — `initialize_flow` (`@start`)

- Sets `ui_status = "researching"`, `current_step = "analyzing_dates"`.
- No crew or LLM work — purely state mutation.

---

### Step 1a — `analyze_travel_dates` (`@listen(initialize_flow)`)

**Short-circuit:** If `confirmed_dates` already has a value (user provided exact ISO dates in the form), the crew is skipped entirely.

**Normal path:**
- Builds a rich `dates_description` injecting: destination list, exact/rough date window, season, duration, all preferences, origin country, and group size.
- Detects `is_rough = not (earliest_possible and latest_possible)`.
- Runs **`TravelCrews.date_scouting_crew(dates_description).kickoff()`**.
- **Rough dates:** appends a strict `IMPORTANT` prompt requiring the `Option N: YYYY-MM-DD to YYYY-MM-DD (N days) - rationale` format; `_parse_multiple_date_ranges()` extracts up to 4 windows into `state.proposed_date_options`, first option set as default `confirmed_dates`.
- **Exact dates:** `_parse_dates_from_text()` extracts the single confirmed range.

---

### Step 1b — `check_date_confirmation` (Human Checkpoint 1)

Decorated with `@listen(analyze_travel_dates)` and `@human_feedback`. The step body broadcasts:
- `"human_feedback_requested"` with `data.proposed_options[]` (rich option cards for rough dates, or single panel for exact dates).
- `"flow_state_update"` — updates the status indicator.

Then `_request_human_feedback()` (overridden on `TravelPlannerFlow`) calls `wait_for_feedback(session_id)` which blocks on the per-session queue.

When the frontend POSTs feedback:
1. If `body.selected_dates` is present, the feedback endpoint looks up `_active_flows[session_id]` and sets `flow.state.confirmed_dates = body.selected_dates` **before** unblocking the queue.
2. The Ollama LLM reads the text and emits `"dates_confirmed"` or `"dates_rejected"`.

---

### Step 2 — `research_destinations` (`@listen("dates_confirmed")`)

Runs **`TravelCrews.destination_research_crew(research_context).kickoff()`**.

Context string explicitly passes `origin_country` and `group_size` so every tool call is preference-aware. Output stored in `state.agent_outputs["destination_research"]`.

---

### Step 3 — `plan_logistics` (`@listen(research_destinations)`)

Runs **`TravelCrews.logistics_crew(trip_details).kickoff()`**.

Context string passes confirmed date range, all preferences, `origin_country`, `group_size`. Output stored in `state.agent_outputs["logistics_plan"]`.

---

### Step 4 — `compile_itinerary` (`@listen(plan_logistics)`)

**No LLM — pure Python:**

1. Regex `Day N - title\n...content...` splits the logistics output into day blocks.
2. `_extract_activities()` extracts bullet/numbered lines per day (capped at 6).
3. Falls back to evenly chunked raw text if structured blocks are absent.
4. Regex `\$[\d,]+` finds the budget estimate.
5. Keyword scan (visa, flight, hotel, etc.) extracts up to 8 key logistics lines.
6. Builds a typed `Itinerary` pydantic object → `state.itinerary`.
7. Broadcasts `"itinerary_ready"` with the full serialised itinerary JSON.

---

### Step 5 — `check_user_confirmation` (Human Checkpoint 2)

Triggered by `or_(compile_itinerary, "needs_revision")` — first compile and any revision loop-back. Same `wait_for_feedback` blocking pattern. Ollama emits `"finalize"` or `"needs_revision"`.

---

### Step 6 — `finalize_trip` (`@listen("finalize")`)

- Sets `ui_status = "complete"`.
- Broadcasts a final `flow_state_update` — UI transitions to the completion screen.

---

## 5. Crew Architecture

Each planning stage is encapsulated in a **`TravelCrews`** factory method. Each method assembles the relevant agents, tasks, and a `Crew` which is then kicked off by the flow step. To extend a stage, add more agents and tasks inside the factory before constructing the `Crew`.

```
TravelCrews
├── date_scouting_crew(context: str) → Crew
│   └── Agents:  [Date Scout]
│   └── Process: sequential
│
├── destination_research_crew(context: str) → Crew
│   └── Agents:  [Destination Expert]
│   └── Process: sequential
│
└── logistics_crew(context: str) → Crew
    └── Agents:  [Logistics Manager]
    └── Process: sequential
```

### Agents & Their Tools

#### Date Scout
> *Analyze fuzzy dates → return 3-4 ISO date range options (rough) or single range (exact)*

| Tool | Purpose | Key Params |
|---|---|---|
| `analyze_fuzzy_dates` | Weather & event research for the date window | `earliest_date`, `latest_date`, `rough_season`, `rough_duration` |
| `check_travel_seasons` | Forecast for a specific month/period | `timeframe` |
| `get_flight_availability` | Flight prices, tips, deals | `origin_country`, `group_size`, `budget_level`, `travel_group_type` |

#### Destination Expert
> *Research destinations → personalised recommendations*

| Tool | Purpose | Key Params |
|---|---|---|
| `research_destination` | Attractions, cuisine, transport, costs | `origin_country`, `group_size` |
| `get_visa_requirements` | Visa rules by passport | `origin_country` (required) |
| `find_accommodations` | Hotel/stay options | `group_size`, `travel_pace` |

#### Logistics Manager
> *Day-by-day itinerary + full logistics plan*

| Tool | Purpose | Key Params |
|---|---|---|
| `plan_transportation` | Flights + local transport | `origin_country`, `group_size` |
| `estimate_budget_breakdown` | Per-day cost estimates | `group_size` |
| `create_daily_itinerary` | Activity planner | (all preferences) |
| `check_travel_insurance` | Insurance options | `origin_country` |

All agents: `LLM = ollama/ministral-3:8b` · `max_iter = 2` · `verbose = False`

---

## 6. Human Feedback System

CrewAI's `@human_feedback` decorator eventually calls `_request_human_feedback()` on the Flow class (which in turn calls `input()`). We override this method directly on `TravelPlannerFlow` to avoid depending on thread-local storage, since CrewAI's `kickoff()` internally uses a `ThreadPoolExecutor` — a different thread than the one `set_thread_session` was called on.

```
@human_feedback decorator
        │
        ▼
TravelPlannerFlow._request_human_feedback(...)  ← overridden
        │
        ▼
_feedback_mod.wait_for_feedback(self.state.session_id)
        │
        ▼
queue.Queue.get(timeout=600)   ← BLOCKS the flow thread
        ▲
        │  queue.put_nowait(feedback_text)
POST /api/plan/{session_id}/feedback
  body: { "feedback_text": "...", "selected_dates": {...} }
        ▲
        │
  User submits HumanFeedbackCard in React frontend
```

### Feedback module public API (`src/feedback.py`)

| Function | Purpose |
|---|---|
| `register_session(id)` | Pre-create the queue slot — call BEFORE spawning the thread |
| `set_thread_session(id)` | Associate current thread with session (legacy / non-flow callers) |
| `submit_feedback(id, text)` | Deliver text to the queue — returns True/False |
| `wait_for_feedback(id, timeout)` | Block current thread until feedback arrives — safe from any thread |
| `has_pending_slot(id)` | Check if a slot exists and is unfilled |
| `cleanup_session(id)` | Remove the queue slot — call in thread's `finally` |

---

## 7. Date Option Selection

When the user enters rough/seasonal dates (no exact ISO window), the Date Scout returns **3–4 concrete travel windows** in `Option N:` format. The full end-to-end selection flow:

```
Backend                              Frontend
───────                              ────────
analyze_travel_dates
  └─ crew output → _parse_multiple_date_ranges()
  └─ state.proposed_date_options = [3-4 options]
  └─ state.confirmed_dates = options[0]  (default)

check_date_confirmation
  └─ _parse_date_options_with_rationale(analysis)
  └─ broadcast({
       type: "human_feedback_requested",
       data: {
         step: "date_confirmation",
         proposed_options: [
           { start, end, duration_days, rationale },
           ...
         ]
       }
     })
                                     HumanFeedbackCard
                                       └─ renders option cards grid
                                       └─ user clicks a card → selectedIdx
                                       └─ "Confirm: Jun 2 – Jun 16" button

POST /api/plan/{id}/feedback
  body: {
    feedback_text: "approve option 2: ...",
    selected_dates: { start_date, end_date, duration_days }
  }

feedback endpoint
  └─ _active_flows[session_id].state.confirmed_dates = selected_dates
  └─ submit_feedback(session_id, text)  ← unblocks queue
```

The `_active_flows` dict maps `session_id → TravelPlannerFlow` and is protected by a `threading.Lock`. This allows the HTTP request handler (on the async event loop) to safely mutate the live flow state before unblocking the queue.

---

## 8. Real-Time Event Pipeline

```
CrewAI Event Bus (global singleton)
        │
        │  WebSocketEventListener  (registered at import of src.listeners)
        │
        ▼
broadcast(data: dict)          ← thread-safe bridge
        │
        │  from worker thread?  → asyncio.run_coroutine_threadsafe(loop)
        │  from event loop?     → asyncio.create_task()
        │
        ▼
_send_all(message: str)
        ├─► WS client 1  /ws/events
        ├─► WS client 2
        └─► ...  (dead sockets silently pruned)
```

### WS Event Types Emitted

| Type | Trigger |
|---|---|
| `crew_kickoff_started / completed / failed` | Crew lifecycle |
| `agent_execution_started / completed` | Agent reasoning |
| `task_started / completed / failed` | Task lifecycle |
| `tool_usage_started / finished / error` | Tool calls |
| `llm_call_started / completed / failed` | LLM prompt/response |
| `flow_method_started / finished / failed` | Flow step lifecycle |
| `human_feedback_requested` | Human checkpoint reached (data contains payload + `proposed_options`) |
| `flow_state_update` | `ui_status` changed |
| `itinerary_ready` | Full itinerary compiled (Step 4) |

---

## 9. Data Model — TravelState

```
TravelState  (extends FlowState)
│
├── session_id: str
├── user_id: Optional[str]
│
├── rough_dates: FuzzyDateRange
│   ├── rough_season     e.g. "summer"
│   ├── rough_duration   e.g. "2 weeks"
│   ├── earliest_possible: Optional[datetime]
│   └── latest_possible:  Optional[datetime]
│
├── destinations: List[DestinationInput]
│   └── { name, type, priority }
│
├── preferences: TravelPreferences
│   ├── budget_level      budget | moderate | luxury
│   ├── travel_pace       relaxed | moderate | fast
│   ├── trip_theme        adventure | cultural | beach | food | ...
│   ├── travel_group_type solo | couple | family | friends
│   ├── group_size        int  (number of travelers)
│   └── origin_country    str  (passport / departure country)
│
├── confirmed_dates: Optional[ConfirmedDateRange]
│   ├── start_date: datetime
│   ├── end_date:   datetime
│   └── duration_days: int
│
├── proposed_date_options: List[ConfirmedDateRange]
│   └── populated when rough dates → 3-4 agent-proposed windows
│
├── agent_outputs: Dict[str, str]
│   ├── "date_analysis"
│   ├── "destination_research"
│   └── "logistics_plan"
│
├── itinerary: Optional[Itinerary]
│   ├── trip_title, destinations, date_range
│   ├── days: List[ItineraryDay]
│   │   └── { day_number, date, title, activities[], notes }
│   ├── summary, estimated_budget
│   └── key_logistics: List[str]
│
├── ui_status: str       (drives frontend status indicator)
└── current_step: str    (drives frontend progress timeline)
```

---

## 10. API Entry Points

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/api/events/kickoff` | Start flow → returns `session_id` immediately (non-blocking) |
| `WS` | `/ws/events` | Real-time event stream (shared across all sessions) |
| `POST` | `/api/plan/{session_id}/feedback` | Submit human feedback text + optional `selected_dates` |
| `POST` | `/api/plan/initialize` | Legacy: session init with Redis persistence |

### Feedback request body schema

```json
{
  "feedback_text": "approve option 2: looks great",
  "selected_dates": {
    "start_date": "2026-06-14",
    "end_date":   "2026-06-28",
    "duration_days": 14
  }
}
```

`selected_dates` is optional — omit for simple approve/reject. When present, the endpoint applies it to `flow.state.confirmed_dates` before unblocking the thread.

---

## 11. Key Design Decisions

| Decision | Rationale |
|---|---|
| **`TravelCrews` factory class** | Encapsulates agent+task+crew assembly per planning stage; adding agents means editing one method, not the flow |
| **`Process.sequential` in every crew** | Straightforward single-agent crews today; switching to `hierarchical` later requires only changing this flag |
| **Background thread, not async** | `Flow.kickoff()` is synchronous/blocking; a thread keeps FastAPI's event loop free |
| **Single global `/ws/events`** | All sessions share one WS channel; clients filter by `session_id` in each message |
| **`_request_human_feedback()` override** | CrewAI's `kickoff()` uses a `ThreadPoolExecutor` internally — a different thread than the one `set_thread_session` targets. Overriding the method uses `self.state.session_id` which is available from any thread via the flow instance |
| **`_active_flows` dict + lock** | Allows the HTTP feedback endpoint to mutate `flow.state.confirmed_dates` before unblocking the queue — essential for preserving the user's date selection |
| **Date options in `proposed_options[]`** | Structured `{start, end, duration_days, rationale}` format enables rich card UI in the frontend without the frontend needing to parse any text |
| **`compile_itinerary` is pure Python** | Avoids a 4th LLM call; regex parsing of structured "Day N" output is fast, deterministic, and cheap |
| **`or_(compile_itinerary, "needs_revision")`** | Makes revision looping explicit; re-runs the review step without re-running expensive research |
| **Ollama for `@human_feedback` LLM** | Keeps all inference local; classifying "approve/reject" is trivial for a small model |
| **`max_iter=2` on all agents** | Hard cap prevents runaway tool loops; 2 iterations is enough for search-then-summarise patterns |
| **Full preference threading** | Every tool receives `origin_country` and `group_size` so web search queries are contextually accurate to the actual traveler |


---

## Table of Contents
1. [High-Level Overview](#1-high-level-overview)
2. [State Machine](#2-state-machine)
3. [Flow Diagram](#3-flow-diagram)
4. [Step-by-Step Walkthrough](#4-step-by-step-walkthrough)
5. [Agents & Their Tools](#5-agents--their-tools)
6. [Human Feedback System](#6-human-feedback-system)
7. [Real-Time Event Pipeline](#7-real-time-event-pipeline)
8. [Data Model — TravelState](#8-data-model--travelstate)
9. [API Entry Points](#9-api-entry-points)
10. [Key Design Decisions](#10-key-design-decisions)

---

## 1. High-Level Overview

```
Browser (React)
    │  POST /api/events/kickoff  ──►  FastAPI (main.py)
    │                                     │
    │  WS  /ws/events  ◄── events ────────┤
    │                                     │
    │  POST /api/plan/{id}/feedback ──►   │
    │                                     ▼
    │                           Background Thread
    │                           TravelPlannerFlow.kickoff()
    │                                     │
    │                          CrewAI Flow State Machine
    │                    (6 steps · 3 Crews · 2 human checkpoints)
```

The backend runs a **CrewAI `Flow`** inside a **background thread** so FastAPI's async event loop is never blocked. All progress streams to the browser over a single **WebSocket** at `/ws/events`.

---

## 2. State Machine

`TravelState` (a `FlowState` subclass) holds all data and drives the UI status indicator.

| `ui_status` value | Meaning |
|---|---|
| `pending` | Session created, flow not yet started |
| `researching` | Flow is actively running agents |
| `awaiting_date_confirmation` | Blocked — waiting for human date approval |
| `awaiting_itinerary_confirmation` | Blocked — waiting for human itinerary review |
| `awaiting_user` | Itinerary compiled, ready to display |
| `complete` | Trip plan finalized |
| `error` | Unrecoverable error |

---

## 3. Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                         TravelPlannerFlow                              │
│                                                                        │
│  ┌──────────────────┐                                                  │
│  │  @start()        │                                                  │
│  │ initialize_flow  │  Sets ui_status="researching"                    │
│  └────────┬─────────┘                                                  │
│           │ @listen(initialize_flow)                                   │
│           ▼                                                            │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  analyze_travel_dates                                    │          │
│  │                                                          │          │
│  │  confirmed_dates already set?                           │          │
│  │    YES ──► skip agent, return immediately               │          │
│  │    NO  ──► run DateScout Crew (max_iter=2)              │          │
│  │              ├─ analyze_fuzzy_dates                      │          │
│  │              ├─ check_travel_seasons                     │          │
│  │              └─ get_flight_availability                  │          │
│  │           regex-parse ISO dates → state.confirmed_dates  │          │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │                                                             │
│           │ @listen(analyze_travel_dates)                               │
│           │ @human_feedback(emit=["dates_confirmed","dates_rejected"])   │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  check_date_confirmation   🛑 HUMAN CHECKPOINT 1          │          │
│  │                                                          │          │
│  │  1. ui_status = "awaiting_date_confirmation"            │          │
│  │  2. broadcast("human_feedback_requested")  ────────────►│──► WS    │
│  │  3. patched input() blocks thread on Queue              │          │
│  │  4. waits for POST /api/plan/{id}/feedback              │          │
│  │     (10-min timeout → default "approve")                │          │
│  │                                                          │          │
│  │  Ollama classifies response ─────────────────────────   │          │
│  │    "dates_confirmed" ──────────────────────────────┐    │          │
│  │    "dates_rejected"  (flow stops / retries)        │    │          │
│  └────────────────────────────────────────────────────┼────┘          │
│                               @listen("dates_confirmed")│               │
│                                                        ▼               │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  research_destinations                                   │          │
│  │                                                          │          │
│  │  DestExpert Crew (max_iter=2):                           │          │
│  │    ├─ research_destination (origin_country, group_size,  │          │
│  │    │    theme, budget, pace)                             │          │
│  │    ├─ get_visa_requirements (origin_country → dest)      │          │
│  │    └─ find_accommodations (group_size, pace, budget)     │          │
│  │                                                          │          │
│  │  → state.agent_outputs["destination_research"]           │          │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │ @listen(research_destinations)                              │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  plan_logistics                                          │          │
│  │                                                          │          │
│  │  LogisticsManager Crew (max_iter=2):                     │          │
│  │    ├─ plan_transportation (origin_country, group_size)   │          │
│  │    ├─ estimate_budget_breakdown (group_size)             │          │
│  │    ├─ create_daily_itinerary (pace, theme, group)        │          │
│  │    └─ check_travel_insurance (origin_country)            │          │
│  │                                                          │          │
│  │  → state.agent_outputs["logistics_plan"]                 │          │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │ @listen(plan_logistics)                                     │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  compile_itinerary   (pure Python — no LLM)              │          │
│  │                                                          │          │
│  │  ├─ regex "Day N" blocks → activities per day            │          │
│  │  ├─ extract $ budget estimate                            │          │
│  │  ├─ extract key logistics lines (visa/flight/hotel...)   │          │
│  │  └─ build Itinerary pydantic object                      │          │
│  │                                                          │          │
│  │  broadcast("itinerary_ready")  ────────────────────────►│──► WS    │
│  └────────────────────────┬─────────────────────────────────┘          │
│           │                             ◄──── loops back on revision   │
│           │ @listen(or_(compile_itinerary, "needs_revision"))           │
│           │ @human_feedback(emit=["finalize","needs_revision"])         │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  check_user_confirmation   🛑 HUMAN CHECKPOINT 2          │          │
│  │                                                          │          │
│  │  1. ui_status = "awaiting_itinerary_confirmation"        │          │
│  │  2. broadcast("human_feedback_requested")  ────────────►│──► WS    │
│  │  3. patched input() blocks thread                        │          │
│  │                                                          │          │
│  │  Ollama classifies response:                             │          │
│  │    "finalize"        ──────────────────────────────────┐ │          │
│  │    "needs_revision"  ──► loops back to this step       │ │          │
│  └────────────────────────────────────────────────────────┼─┘          │
│                                  @listen("finalize")       │            │
│                                                            ▼            │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  finalize_trip                                           │          │
│  │  ui_status = "complete"                                  │          │
│  │  broadcast("flow_state_update")  ──────────────────────►│──► WS    │
│  └──────────────────────────────────────────────────────────┘          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Step-by-Step Walkthrough

### Step 0 — Session Kickoff (`POST /api/events/kickoff`)

1. FastAPI creates a UUID `session_id` and a `TravelState` from the request body.
2. `feedback_mod.register_session(session_id)` pre-creates a `queue.Queue(maxsize=1)` **before** the thread starts so `input()` has a slot to block on immediately.
3. A **daemon thread** is spawned. Inside it: `set_thread_session` binds the session ID to Python thread-local storage, then `flow.kickoff()` is called synchronously.
4. The thread's `finally` block always calls `cleanup_session` to remove the queue.
5. FastAPI immediately returns `{"status": "started", "session_id": "..."}` — fully non-blocking.

---

### Step 1 — `initialize_flow` (`@start`)

- Sets `ui_status = "researching"`, `current_step = "analyzing_dates"`.
- No agent or LLM work — purely state mutation.

---

### Step 1a — `analyze_travel_dates` (`@listen(initialize_flow)`)

**Short-circuit:** If `confirmed_dates` already has a value (user provided exact ISO dates in the form), the agent is skipped entirely.

**Normal path:**
- Builds a rich `dates_description` injecting: destination list, exact/rough date window, season, duration, all preferences, origin country, and group size.
- Runs a single-agent **DateScout Crew** (`max_iter=2`).
- `_parse_dates_from_text()` regex-scans the agent's output for two `YYYY-MM-DD` patterns and populates `confirmed_dates`.

---

### Step 1b — `check_date_confirmation` (Human Checkpoint 1)

Decorated with both `@listen(analyze_travel_dates)` and `@human_feedback`. CrewAI executes the step body, then calls `input()` — which is the patched version.

The **patched `input()`**:
1. Reads `session_id` from thread-local storage.
2. Finds that session's `queue.Queue`.
3. Calls `q.get(timeout=600)` — **blocks the flow thread for up to 10 minutes**.

Meanwhile, the step body has already broadcast:
- `"human_feedback_requested"` — triggers the `HumanFeedbackCard` in the UI.
- `"flow_state_update"` — updates the status indicator.

When the user submits feedback, `POST /api/plan/{session_id}/feedback` puts the text into the queue. The Ollama LLM reads the text and emits `"dates_confirmed"` or `"dates_rejected"`.

---

### Step 2 — `research_destinations` (`@listen("dates_confirmed")`)

Runs the **DestExpert Crew**. The task description explicitly instructs the agent to:
- Pass `origin_country` to `get_visa_requirements` and `research_destination`.
- Pass `group_size` to `find_accommodations`.

Output stored in `state.agent_outputs["destination_research"]`.

---

### Step 3 — `plan_logistics` (`@listen(research_destinations)`)

Runs the **LogisticsManager Crew**. Task description mandates:
- `plan_transportation` ← `origin_country`, `group_size`
- `estimate_budget_breakdown` ← `group_size`
- `check_travel_insurance` ← `origin_country`

Output stored in `state.agent_outputs["logistics_plan"]`.

---

### Step 4 — `compile_itinerary` (`@listen(plan_logistics)`)

**No LLM — pure Python:**

1. Regex `Day N - title\n...content...` splits the logistics output into day blocks.
2. `_extract_activities()` extracts bullet/numbered lines per day (capped at 6).
3. Falls back to evenly chunked raw text if structured day blocks are missing.
4. Regex `\$[\d,]+` finds the budget estimate.
5. Keyword scan extracts up to 8 key logistics lines (visa, flight, hotel, etc.).
6. Builds a typed `Itinerary` pydantic object → `state.itinerary`.
7. Broadcasts `"itinerary_ready"` with the full serialized itinerary JSON.

---

### Step 5 — `check_user_confirmation` (Human Checkpoint 2)

Triggered by `or_(compile_itinerary, "needs_revision")` — so it activates on the **first compile** and also whenever the user requests changes (loop-back).

Same blocking pattern as Checkpoint 1. Ollama emits `"finalize"` or `"needs_revision"`. If revision is requested, the `or_` condition re-triggers this same step.

---

### Step 6 — `finalize_trip` (`@listen("finalize")`)

- Sets `ui_status = "complete"`.
- Broadcasts a final `flow_state_update` — UI transitions to the completion screen.

---

## 5. Agents & Their Tools

### DateScout Agent
> *Analyze fuzzy dates → return precise ISO date range*

| Tool | Purpose | Added Params |
|---|---|---|
| `analyze_fuzzy_dates` | Weather & event research for the date window | `earliest_date`, `latest_date`, `rough_season`, `rough_duration` |
| `check_travel_seasons` | Forecast for a specific month/period | `timeframe` |
| `get_flight_availability` | Flight prices, tips, deals | `origin_country`, `group_size`, `budget_level`, `travel_group_type` |

### DestExpert Agent
> *Research destinations → personalised recommendations*

| Tool | Purpose | Added Params |
|---|---|---|
| `research_destination` | Attractions, cuisine, transport, costs | `origin_country`, `group_size` |
| `get_visa_requirements` | Visa rules by passport | `origin_country` (required) |
| `find_accommodations` | Hotel/stay options | `group_size`, `travel_pace` |

### LogisticsManager Agent
> *Day-by-day itinerary + full logistics plan*

| Tool | Purpose | Added Params |
|---|---|---|
| `plan_transportation` | Flights + local transport | `origin_country`, `group_size` |
| `estimate_budget_breakdown` | Per-day cost estimates | `group_size` |
| `create_daily_itinerary` | Activity planner | (all preferences) |
| `check_travel_insurance` | Insurance options | `origin_country` |

All agents: `LLM = ollama/ministral-3:8b` · `max_iter = 2` · `verbose = False`

---

## 6. Human Feedback System

The core mechanism is a **monkey-patched `builtins.input()`** installed once at module import time.

```
import src.feedback       ← patches builtins.input = _patched_input

@human_feedback decorator calls input("prompt...")
        │
        ▼
_patched_input()
  1. read _local.session_id  (set by set_thread_session inside the thread)
  2. _queues[session_id]      (created by register_session before thread start)
  3. q.get(timeout=600)       ← BLOCKS flow thread up to 10 minutes
        ▲
        │  q.put_nowait(text)
POST /api/plan/{session_id}/feedback
  body: { "feedback_text": "looks good, approve" }
        ▲
        │
  User clicks Approve/Reject in HumanFeedbackCard (React)
```

After `input()` unblocks and returns the text, the Ollama LLM classifier (specified via `llm=_FEEDBACK_LLM` on the decorator) reads that text and emits the matching outcome token to drive the flow forward.

---

## 7. Real-Time Event Pipeline

```
CrewAI Event Bus (global singleton)
        │
        │  WebSocketEventListener  (registered at import of src.listeners)
        │
        ▼
broadcast(data: dict)          ← thread-safe bridge
        │
        │  from worker thread?  → asyncio.run_coroutine_threadsafe(loop)
        │  from event loop?     → asyncio.create_task()
        │
        ▼
_send_all(message: str)
        ├─► WS client 1  /ws/events
        ├─► WS client 2
        └─► ...  (dead sockets silently pruned)
```

### WS Event Types Emitted

| Type | Trigger |
|---|---|
| `crew_kickoff_started / completed / failed` | Crew lifecycle |
| `agent_execution_started / completed` | Agent reasoning |
| `task_started / completed / failed` | Task lifecycle |
| `tool_usage_started / finished / error` | Tool calls |
| `llm_call_started / completed / failed` | LLM prompt/response |
| `flow_method_started / finished / failed` | Flow step lifecycle |
| `human_feedback_requested` | Human checkpoint reached |
| `flow_state_update` | `ui_status` changed |
| `itinerary_ready` | Full itinerary compiled (Step 4) |

---

## 8. Data Model — TravelState

```
TravelState  (extends FlowState)
│
├── session_id: str
├── user_id: Optional[str]
│
├── rough_dates: FuzzyDateRange
│   ├── rough_season     e.g. "summer"
│   ├── rough_duration   e.g. "2 weeks"
│   ├── earliest_possible: Optional[datetime]
│   └── latest_possible:  Optional[datetime]
│
├── destinations: List[DestinationInput]
│   └── { name, type, priority }
│
├── preferences: TravelPreferences
│   ├── budget_level      budget | moderate | luxury
│   ├── travel_pace       relaxed | moderate | fast
│   ├── trip_theme        adventure | cultural | beach | food | ...
│   ├── travel_group_type solo | couple | family | friends
│   ├── group_size        int  (number of travelers)
│   └── origin_country    str  (passport / departure country)
│
├── confirmed_dates: Optional[ConfirmedDateRange]
│   ├── start_date: datetime
│   ├── end_date:   datetime
│   └── duration_days: int
│
├── agent_outputs: Dict[str, str]
│   ├── "date_analysis"
│   ├── "destination_research"
│   └── "logistics_plan"
│
├── itinerary: Optional[Itinerary]
│   ├── trip_title, destinations, date_range
│   ├── days: List[ItineraryDay]
│   │   └── { day_number, date, title, activities[], notes }
│   ├── summary, estimated_budget
│   └── key_logistics: List[str]
│
├── ui_status: str       (drives frontend status indicator)
└── current_step: str    (drives frontend progress timeline)
```

---

## 9. API Entry Points

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/api/events/kickoff` | Start flow → returns `session_id` (non-blocking) |
| `WS` | `/ws/events` | Real-time event stream (shared across all sessions) |
| `POST` | `/api/plan/{session_id}/feedback` | Submit human feedback text to unblock flow |
| `POST` | `/api/plan/initialize` | Legacy: session init with Redis persistence |

---

## 10. Key Design Decisions

| Decision | Rationale |
|---|---|
| **Background thread, not async** | `Flow.kickoff()` is synchronous/blocking; a thread keeps FastAPI's event loop free |
| **Single global `/ws/events`** | All sessions share one WS channel; clients filter by `session_id` in each message |
| **`builtins.input()` monkey-patch** | CrewAI's `@human_feedback` calls `input()` internally; patching is non-invasive — no CrewAI fork needed |
| **Thread-local `session_id`** | Multiple sessions run concurrently in separate threads; thread-local is the natural way to associate "which queue am I blocking on?" |
| **compile_itinerary is pure Python** | Avoids a 4th LLM call; regex parsing of structured "Day N" output is fast, deterministic, and cheap |
| **`or_(compile_itinerary, "needs_revision")`** | Makes revision looping explicit; the same review step re-runs cleanly without re-running the expensive research steps |
| **Ollama for `@human_feedback` LLM** | Keeps all inference local; classifying "approve/reject" is trivial for a small model |
| **`max_iter=2` on all agents** | Hard cap prevents runaway tool loops; 2 iterations is enough for search-then-summarise patterns |
| **Full preference threading** | Every tool now receives `origin_country` and `group_size`, so every web search query is contextually accurate to the actual traveler |