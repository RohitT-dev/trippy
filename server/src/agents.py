"""CrewAI Agent and Crew Definitions for Travel Planning"""

import os
from typing import Any, Tuple
from pydantic import BaseModel, Field
from crewai import Agent, Task, Crew, LLM
from crewai import Process
from crewai.tools import tool
from .tools.date_tools import (
    analyze_fuzzy_dates,
    check_travel_seasons,
    get_flight_availability
)
from .tools.destination_tools import (
    research_destination,
    get_visa_requirements,
    find_accommodations
)
from .tools.logistics_tools import (
    plan_transportation,
    estimate_budget_breakdown,
    create_daily_itinerary,
    check_travel_insurance
)


# ---------------------------------------------------------------------------
# Structured output models
# ---------------------------------------------------------------------------

class DateWindow(BaseModel):
    start_date: str
    end_date: str
    days: int
    rationale: str


class DateSynthesisOutput(BaseModel):
    options: list[DateWindow]


class FuzzyDateAnalysisOutput(BaseModel):
    """Structured output from Fuzzy Date Analyst agent."""
    destination: str
    candidate_windows: list[DateWindow] = Field(..., description="1-3 windows from tool only")
    confidence: float = Field(ge=0, le=1, description="Confidence (0-1)")
    source: str = Field(default="analyze_fuzzy_dates")


class SeasonalAnalysisOutput(BaseModel):
    """Structured output from Travel Season Analyst."""
    destination: str
    weather_summary: str
    crowd_level: str = Field(description="peak, shoulder, or off-season")
    notable_events: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    source: str = Field(default="check_travel_seasons")


class FlightOption(BaseModel):
    route: str
    airlines: list[str]
    price_range: str = Field(description="e.g. '$400-600' or 'INSUFFICIENT_DATA'")


class FlightScoutOutput(BaseModel):
    """Structured output from Flight Scout agent."""
    destination: str
    flight_options: list[FlightOption]
    booking_window: str
    confidence: float = Field(ge=0, le=1)
    source: str = Field(default="get_flight_availability")


class DestinationResearchOutput(BaseModel):
    """Structured output from Destination Expert agent."""
    destination: str
    attractions: list[str] = Field(..., description="From tool data only")
    activities: list[str]
    visa_info: str
    accommodation_summary: str
    avg_daily_cost: str
    confidence: float = Field(ge=0, le=1)
    source: str = Field(default="research_destination")


class DayItinerary(BaseModel):
    day_number: int
    destination_name: str
    activities: list[str] = Field(max_items=5, description="Max 5 activities per day")


class LogisticsOutput(BaseModel):
    """Structured output from Logistics Manager agent."""
    itinerary: list[DayItinerary]
    estimated_total_budget: str = Field(description="e.g. '$2500'")
    key_logistics: str
    confidence: float = Field(ge=0, le=1)


class TripOutlineOutput(BaseModel):
    """Structured output from Trip Interpreter agent."""
    trip_vibe: str
    destinations_summary: str
    implicit_needs: str
    ideal_date_window: str
    budget_assessment: str


# ---------------------------------------------------------------------------
# Task guardrails
# ---------------------------------------------------------------------------

def _validate_four_options(result) -> Tuple[bool, Any]:
    """Ensure the synthesis task returns exactly 4 date window options."""
    if result.pydantic and len(result.pydantic.options) == 4:
        return (True, result)
    return (False, "Must return exactly 4 date window options.")


def _validate_no_hallucination_flights(result) -> Tuple[bool, Any]:
    """Ensure Flight Scout only uses tool data, never guesses prices."""
    if not result.pydantic or not result.pydantic.flight_options:
        return (False, "No flight options. If tool had no data, output flight_options: []")
    # Reject vague price estimates
    for opt in result.pydantic.flight_options:
        if any(word in opt.price_range.lower() for word in ["guess", "estimate", "probably", "approximately"]):
            return (False, "Flight prices must come from tool data or say 'INSUFFICIENT_DATA', never guess.")
    return (True, result)


def _validate_logistics_pacing(result) -> Tuple[bool, Any]:
    """Ensure itineraries have realistic daily pacing (max 5 activities/day)."""
    if not result.pydantic:
        return (False, "Invalid output format.")
    for day in result.pydantic.itinerary:
        if len(day.activities) > 5:
            return (False, f"Day {day.day_number} has {len(day.activities)} activities (max 5 allowed).")
    return (True, result)


def _validate_no_budget_hallucination(result) -> Tuple[bool, Any]:
    """Ensure Trip Interpreter doesn't estimate costs without data."""
    if not result.pydantic:
        return (False, "Invalid output format.")
    # Check budget_assessment for hallucinated price numbers without context
    budget = result.pydantic.budget_assessment.lower()
    # Flag vague numerical claims without explicit source
    if any(pattern in budget for pattern in ["$", "USD", "per day", "per night"]):
        if "INSUFFICIENT_DATA" not in budget and "tool data" not in budget and "budget breakdown" not in budget:
            return (False, 
                "Budget estimates must cite tool data or explicitly say INSUFFICIENT_DATA. "
                "Trip Interpreter has no tool access — don't estimate costs.")
    return (True, result)


def _validate_destination_pricing_honesty(result) -> Tuple[bool, Any]:
    """Ensure Destination Expert doesn't hallucinate accommodation costs."""
    if not result.pydantic:
        return (False, "Invalid output format.")
    accom = result.pydantic.accommodation_summary.lower()
    if any(pattern in accom for pattern in ["$", "USD", "per night", "per room"]):
        if "INSUFFICIENT_DATA" not in accom and "tool data" not in accom and "find_accommodations" not in accom:
            return (False,
                "Accommodation costs must come from find_accommodations tool or say INSUFFICIENT_DATA. "
                "Don't estimate prices.")
    return (True, result)


class TravelAgents:
    """Collection of agents for travel planning"""

    @staticmethod
    def _get_llm(tier: str = "standard") -> LLM | None:
        """Get a configured LLM for the requested capability tier.

        Tiers:
          fast      - lightweight model for single-tool callers
          standard  - balanced model for research / logistics agents
          reasoning - larger / reasoning-optimised model for synthesis & manager agents

        Override Ollama model names via env vars:
          OLLAMA_MODEL_FAST, OLLAMA_MODEL (standard), OLLAMA_MODEL_REASONING
        """
        llm_provider = os.getenv("LLM_PROVIDER", "ollama")

        if llm_provider == "ollama":
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            _standard = os.getenv("OLLAMA_MODEL", "ministral-3:8b")
            models = {
                "fast":      os.getenv("OLLAMA_MODEL_FAST", "qgranite4:3b"),
                "standard":  _standard,
                "reasoning": os.getenv("OLLAMA_MODEL_REASONING", _standard),
            }
            model = models.get(tier, _standard)
            return LLM(model=f"ollama/{model}", base_url=base_url)
        else:
            # For OpenAI-compatible providers, model selection is handled externally
            return None  # CrewAI will use default OpenAI

    @staticmethod
    def fuzzy_date_analyst_agent() -> Agent:
        """
        Specialist: parses vague or seasonal date inputs into concrete date windows.
        Sole tool: analyze_fuzzy_dates.
        
        STRICT RULES:
        - ONLY return dates provided by analyze_fuzzy_dates tool
        - NEVER generate or invent dates yourself
        - If tool returns insufficient/no data → explicitly output INSUFFICIENT_DATA
        """
        return Agent(
            role="Fuzzy Date Analyst",
            goal=(
                "Parse vague or seasonal travel date inputs into concrete candidate date windows "
                "for {destination_name} using ONLY data from the analyze_fuzzy_dates tool."
            ),
            backstory=(
                "You are an expert at decoding imprecise travel timelines. You ONLY use "
                "analyze_fuzzy_dates to turn descriptions like 'summer' into concrete date windows. "
                "You NEVER invent dates or make assumptions."
            ),
            tools=[analyze_fuzzy_dates],
            llm=TravelAgents._get_llm("fast"),
            max_iter=2,
            inject_date=True,
            date_format="%Y-%m-%d",
            cache=True,
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: no creative date invention
        )

    @staticmethod
    def travel_season_analyst_agent() -> Agent:
        """
        Specialist: evaluates seasonal weather, crowd levels, and events for a destination.
        Sole tool: check_travel_seasons.
        
        STRICT RULES:
        - ONLY report facts provided by check_travel_seasons tool
        - For every claim (weather, events), cite the tool
        - If data missing → say INSUFFICIENT_DATA, never fabricate
        """
        return Agent(
            role="Travel Season Analyst",
            goal=(
                "Research seasonal weather, crowd levels, and events for {destination_name} "
                "in the relevant travel window using ONLY data from check_travel_seasons."
            ),
            backstory=(
                "You are a destination climate specialist. You use check_travel_seasons to fetch "
                "seasonal intelligence. You ONLY report facts from the tool. You NEVER guess weather "
                "or events."
            ),
            tools=[check_travel_seasons],
            llm=TravelAgents._get_llm("fast"),
            max_iter=2,
            inject_date=True,
            date_format="%Y-%m-%d",
            cache=True,
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: no speculation on weather/events
        )

    @staticmethod
    def flight_scout_agent() -> Agent:
        """
        Specialist: researches flight availability, pricing, and booking tips.
        Sole tool: get_flight_availability.
        
        CRITICAL ANTI-HALLUCINATION RULES:
        - NEVER estimate flight prices without tool data
        - If tool returns no prices → output price_range: "INSUFFICIENT_DATA"
        - NEVER say "approximately" or "likely" prices
        - All data must come from get_flight_availability
        """
        return Agent(
            role="Flight Scout",
            goal=(
                "Research flight availability and pricing for {destination_name} "
                "using ONLY data from get_flight_availability. NEVER guess prices."
            ),
            backstory=(
                "You are a flights specialist. You use get_flight_availability to fetch real "
                "routing and pricing data. You NEVER estimate or hallucinate prices. "
                "If the tool has no data, you explicitly say so."
            ),
            tools=[get_flight_availability],
            llm=TravelAgents._get_llm("fast"),
            max_iter=2,
            cache=True,
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: zero tolerance for price hallucination
        )

    @staticmethod
    def date_scout_manager_agent() -> Agent:
        """
        Manager: orchestrates the three date-scouting specialists and synthesises
        their findings into a concise date-scouting report. No tools — pure reasoning.
        
        CRITICAL ANTI-HALLUCINATION RULES:
        - ONLY synthesize findings from the Flight Scout, Fuzzy Analyst, Season Analyst
        - NEVER add price estimates not provided by Flight Scout
        - If Flight Scout reports INSUFFICIENT_DATA → pass that through unchanged
        - NEVER "fill in" missing price data
        """
        return Agent(
            role="Date Scout Manager",
            goal=(
                "Delegate date-research work to the right specialists, then synthesise their "
                "findings into a concise, well-structured date-scouting report for "
                "{destination_name}. ONLY report data provided by your specialists."
            ),
            backstory=(
                "You are a senior travel research manager who leads a team of date-scouting "
                "specialists. You direct your Fuzzy Date Analyst, Travel Season Analyst, and "
                "Flight Scout to each do their focused research, then you combine their outputs "
                "into a clear summary that the downstream planning stages can use directly. "
                "You NEVER guess or fabricate data — you only synthesize what your team found."
            ),
            tools=[],  # orchestrator only — no direct tool calls
            llm=TravelAgents._get_llm("reasoning"),
            max_iter=2,
            inject_date=True,
            date_format="%Y-%m-%d",
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: no creative synthesis of pricing
        )

    @staticmethod
    def destination_expert_agent() -> Agent:
        """
        DestExpert agent: Specialized in destination research and recommendations.
        
        CRITICAL ANTI-HALLUCINATION RULES:
        - NEVER estimate costs, accommodation prices, or activity fees without tool data
        - For any pricing question → use find_accommodations tool or explicitly say INSUFFICIENT_DATA
        - NEVER say "typically costs" or "usually runs about" unless tool provided the data
        """
        return Agent(
            role="Destination Expert",
            goal=(
                "Research destinations thoroughly using ONLY tool data. "
                "NEVER estimate prices. If tools lack pricing data → explicitly say so."
            ),
            backstory="""You are a seasoned travel consultant who has visited hundreds of destinations.
            You know the hidden gems, the best activities, visa requirements, cuisine, culture, and logistics
            for destinations around the world. You tailor recommendations based on travel style and preferences.
            When it comes to pricing, you ONLY report what your tools provide. You NEVER guess costs.""",
            tools=[
                research_destination,
                get_visa_requirements,
                find_accommodations,
            ],
            llm=TravelAgents._get_llm("standard"),
            max_iter=2,
            cache=True,
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: prevent price hallucination
        )

    @staticmethod
    def logistics_manager_agent() -> Agent:
        """
        LogisticsManager agent: Specialized in planning trip logistics and itineraries.
        
        CRITICAL ANTI-HALLUCINATION RULES:
        - NEVER estimate transportation costs, activity fees, or meal prices without tool data
        - For budget calculations → ONLY use estimate_budget_breakdown tool results
        - NEVER say "expect to spend" or "budget roughly X" unless tool data supports it
        - Estimated totals must cite the tool or explicitly say INSUFFICIENT_DATA
        """
        return Agent(
            role="Logistics Manager",
            goal=(
                "Create comprehensive travel logistics and day-by-day itineraries "
                "using ONLY tool data for cost estimates. NEVER guess budget numbers."
            ),
            backstory="""You are a masterful trip planner who excels at optimizing travel logistics, budgets,
            and itineraries. You understand transportation, accommodation, budgeting, and can create detailed
            daily plans that balance activities, rest, and practical considerations. You always prioritize
            traveler comfort and safety. For any cost estimate, you use estimate_budget_breakdown and NEVER guess.""",
            tools=[
                plan_transportation,
                estimate_budget_breakdown,
                create_daily_itinerary,
                check_travel_insurance,
            ],
            llm=TravelAgents._get_llm("standard"),
            max_iter=2,
            cache=True,
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: prevent cost hallucination
        )

    @staticmethod
    def date_synthesizer_agent() -> Agent:
        """
        DateSynthesizer agent: Combines per-destination date analysis results into
        exactly 4 travel windows that work for ALL destinations simultaneously.
        No tools — it reasons purely over the provided context.
        
        CRITICAL ANTI-HALLUCINATION RULES:
        - ONLY synthesize seasonal/weather data, NOT pricing
        - If any window lacks seasonal data for a destination → mark as UNCERTAIN
        - NEVER add flight price predictions to the date windows
        - Price info comes from Flight Scout data — pass it through don't modify
        """
        return Agent(
            role="Date Synthesizer",
            goal=(
                "Analyse the date research reports for multiple destinations and produce "
                "exactly 4 concrete travel date windows that are simultaneously ideal for "
                "every destination. Each window must match the user's requested trip duration "
                "and include a rationale that mentions every destination by name. "
                "Focus on seasonal/weather alignment — pricing is separate."
            ),
            backstory=(
                "You are a senior travel strategist who specialises in multi-destination trip "
                "planning. You read per-destination seasonal research and identify the windows "
                "of time where weather, events, and crowds align well across all locations at once. "
                "You are precise with dates and always justify each suggestion clearly. "
                "You NEVER attempt to synthesize or predict flight prices — that's the Flight Scout's job."
            ),
            tools=[],  # Pure reasoning — no tool calls needed
            llm=TravelAgents._get_llm("reasoning"),
            max_iter=2,
            inject_date=True,
            date_format="%Y-%m-%d",
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: no price invention during synthesis
        )

    @staticmethod
    def trip_interpreter_agent() -> Agent:
        """
        TripInterpreter agent: parses the user's natural-language description and
        preferences into a structured, richly-detailed trip outline.
        No tools — pure reasoning over the provided context.
        
        CRITICAL ANTI-HALLUCINATION RULES:
        - Do NOT estimate costs or budgets based on destinations
        - Budget assessment → focus on feasibility check, NOT price estimation
        - If you cannot judge a budget without pricing data → say INSUFFICIENT_DATA
        """
        return Agent(
            role="Trip Interpreter",
            goal=(
                "Read the traveller\'s own words and stated preferences, then produce a clear, "
                "structured outline of what this trip should look and feel like: the vibe, "
                "key experiences, estimated pace per destination, and any implicit needs "
                "(accessibility, dietary, etc.). This outline will guide every downstream "
                "planning step. Do NOT estimate costs in this phase."
            ),
            backstory=(
                "You are a master travel consultant who excels at translating vague travel "
                "dreams into concrete, actionable trip blueprints. You read between the lines "
                "of a traveller\'s description — picking up on tone, priorities, and unstated "
                "expectations — and produce structured outlines that set the other planning "
                "agents up for success. You focus on vibe and experience — pricing comes later."
            ),
            tools=[],
            llm=TravelAgents._get_llm("standard"),
            max_iter=2,
            inject_date=True,
            date_format="%Y-%m-%d",
            respect_context_window=True,
            verbose=False,
            temperature=0.0,  # ← Deterministic: no budget speculation
        )

class TravelCrews:
    """Factory for travel-planning Crews.

    Each method assembles the relevant Agents, Tasks, and a Crew for one
    planning stage.  To extend a stage, instantiate additional agents here,
    create their Tasks, and add them to the ``agents`` / ``tasks`` lists
    before constructing the Crew.
    """

    @staticmethod
    def trip_outline_crew(description: str, pref_summary: str, task_callback=None) -> Crew:
        """Crew that interprets the user\'s natural-language trip description and
        preferences into a detailed, structured trip outline.

        Args:
            description:  Raw NL text the traveller typed.
            pref_summary: Pre-formatted preference + profile summary string.
        """
        interpreter = TravelAgents.trip_interpreter_agent()

        task = Task(
            description=(
                f"Traveller\'s own words:\n\"{description}\"\n\n"
                f"Traveller profile & preferences:\n{pref_summary}\n\n"
                "Produce a BASIC trip outline guide (NOT a plan) that helps other agents understand the trip.\n"
                "Include ONLY:\n"
                "1. Trip Vibe — the overall feeling and purpose of the trip (1-2 sentences). What\'s the essence?\n"
                "2. Destinations Listed — just list the destinations by name.\n"
                "3. Rough Timeline — how many days total? When (season/rough dates)?\n"
                "4. Key Preferences — what matters most to this traveller? "
                "(budget level, travel pace, group type, interests/themes)\n"
                "5. Special Considerations — any accessibility, dietary, photography, family, or romantic focus?\n\n"
                "DO NOT include:\n"
                "- Specific activities or itineraries (that\'s for other agents)\n"
                "- Detailed research or highlights\n"
                "- Cost estimates\n\n"
                "This outline guides date scouts, destination researchers, and logistics planners. "
                "Keep it concise and factual."
            ),
            agent=interpreter,
            output_pydantic=TripOutlineOutput,
            guardrail=_validate_no_budget_hallucination,
            guardrail_max_retries=2,
            max_retry_limit=0,
            markdown=True,
            expected_output=(
                "Structured trip outline with five clearly-labelled sections: "
                "Trip Vibe & Theme, Destinations & Highlights, Implicit Needs, "
                "Ideal Date Constraints, and Budget Sense-check (without cost estimates)."
            ),
        )

        return Crew(
            agents=[interpreter],
            tasks=[task],
            process=Process.sequential,
            cache=True,
            task_callback=task_callback,
            verbose=True,
        )

    @staticmethod
    def date_scouting_crew(task_callback=None) -> Crew:
        """Hierarchical crew that analyses travel dates for a single destination.

        Three specialist agents each handle one research dimension; a manager agent
        orchestrates them and synthesises the final concise report.

        Designed for parallel execution via ``kickoff_for_each_async``.
        Task placeholders (supplied via the inputs dict):
            {destination_name}     – single destination to research, e.g. "Tokyo"
            {date_ctx}             – pre-formatted date context string
            {pref_context}         – pre-formatted preferences & origin string
            {is_rough_instruction} – empty string for exact dates; the
                                     "IMPORTANT: return 3–4 options…" block for rough dates
        """
        fuzzy_analyst = TravelAgents.fuzzy_date_analyst_agent()
        season_analyst = TravelAgents.travel_season_analyst_agent()
        flight_scout   = TravelAgents.flight_scout_agent()
        manager        = TravelAgents.date_scout_manager_agent()

        fuzzy_task = Task(
            description=(
                "Interpret the travel date input for {destination_name} and identify "
                "concrete candidate date windows.\n\n"
                "Date context: {date_ctx}\n"
                "{pref_context}\n\n"
                "Call analyze_fuzzy_dates with:\n"
                "- destination = {destination_name}\n"
                "- Date fields from the date context above:\n"
                "  rough dates → rough_season / rough_duration\n"
                "  exact dates → earliest_date / latest_date\n\n"
                "Return the candidate windows with a brief 2–3 sentence interpretation.\n\n"
                "{is_rough_instruction}"
            ),
            agent=fuzzy_analyst,
            max_retry_limit=0,
            expected_output=(
                "Candidate date windows for {destination_name} with start/end date ranges "
                "and a short explanation derived from the fuzzy date analysis."
            ),
        )

        season_task = Task(
            description=(
                "Research seasonal travel conditions for {destination_name} in the "
                "relevant travel window.\n\n"
                "Date context: {date_ctx}\n"
                "{pref_context}\n\n"
                "Call check_travel_seasons with:\n"
                "- destination = {destination_name}\n"
                "- timeframe derived from the date context "
                "(e.g. 'June 2026', 'summer 2026', 'Jun–Jul 2026').\n\n"
                "Report weather patterns, crowd levels, notable events, and whether the "
                "window is peak / shoulder / off-season for {destination_name}."
            ),
            agent=season_analyst,
            max_retry_limit=0,
            expected_output=(
                "Seasonal summary for {destination_name}: weather, crowd levels, key events, "
                "and peak / shoulder / off-season classification for the relevant window."
            ),
        )

        flight_task = Task(
            description=(
                "Research flight availability and pricing for travel to {destination_name}.\n\n"
                "Date context: {date_ctx}\n"
                "{pref_context}\n\n"
                "Call get_flight_availability with:\n"
                "- destination = {destination_name}\n"
                "- Traveller context from {pref_context}: origin_country, group_size, "
                "budget_level, travel_group_type.\n"
                "- Exact ISO dates → start_date / end_date; rough dates → descriptive string.\n\n"
                "Report available routes, rough price ranges, and booking recommendations.\n\n"
                "CRITICAL: All price ranges MUST come from get_flight_availability tool. "
                "If no pricing data, output price_range='INSUFFICIENT_DATA'. NEVER guess prices."
            ),
            agent=flight_scout,
            output_pydantic=FlightScoutOutput,
            guardrail=_validate_no_hallucination_flights,
            guardrail_max_retries=2,
            max_retry_limit=0,
            expected_output=(
                "Flight summary for {destination_name}: route options, price ranges "
                "(from tool data or INSUFFICIENT_DATA), and booking tips tailored to the traveller profile."
            ),
        )

        return Crew(
            agents=[fuzzy_analyst, season_analyst, flight_scout],
            tasks=[fuzzy_task, season_task, flight_task],
            process=Process.hierarchical,
            manager_agent=manager,
            cache=True,
            task_callback=task_callback,
            verbose=True,
        )

    @staticmethod
    def date_synthesis_crew(
        executed_scouting_crews: list,
        dest_names: list[str],
        pref_context: str,
        requested_days: int | None = None,
        task_callback=None,
    ) -> Crew:
        """Crew that synthesises per-destination date-scouting results into
        4 combined travel windows suitable for ALL destinations.

        The synthesis task receives the scouting outputs via CrewAI's native
        ``Task.context`` mechanism — every task from every executed scouting
        crew is listed as context so CrewAI injects their outputs automatically.

        Args:
            executed_scouting_crews: Crew instances that have already been run
                                     (``crew.tasks`` have ``.output`` populated).
            dest_names:   Destination names in the same order as the crews.
            pref_context: Pre-formatted user-preferences string.
            requested_days: Exact trip length in days, or None if unspecified.
        """
        synthesizer = TravelAgents.date_synthesizer_agent()

        # Collect all tasks whose outputs are already populated by the scouting
        # execution.  CrewAI will inject each task.output.raw into the synthesis
        # task's prompt context block automatically.
        context_tasks: list = []
        for crew in executed_scouting_crews:
            context_tasks.extend(crew.tasks)

        duration_constraint = (
            f"Each option MUST span EXACTLY {requested_days} days "
            f"(the user's requested trip duration).\n"
        ) if requested_days else ""

        task = Task(
            description=(
                f"Destinations to cover: {', '.join(dest_names)}\n"
                f"{duration_constraint}"
                f"User preferences: {pref_context}\n\n"
                "The date scouting reports for every destination are available in your "
                "context (injected above by the system). Read them carefully.\n\n"
                "Your task:\n"
                "Identify up to 4 date windows where the conditions are simultaneously "
                "good for EVERY destination listed. "
                "Each window MUST:\n"
                "- Match the requested trip duration exactly (if specified above).\n"
                "- Be a future date (after today).\n"
                "- Include a rationale that explicitly mentions each destination and why "
                "that window works for it (weather, events, crowds, etc.).\n\n"
                "Output EXACTLY in this format, no other text:\n"
                "Option 1: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale mentioning every destination>\n"
                "Option 2: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale mentioning every destination>\n"
                "Option 3: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale mentioning every destination>\n"
                "Option 4: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale mentioning every destination>"
            ),
            agent=synthesizer,
            context=context_tasks,  # ← scouting outputs injected here by CrewAI
            output_pydantic=DateSynthesisOutput,
            guardrail=_validate_four_options,
            guardrail_max_retries=3,
            max_retry_limit=0,
            markdown=True,
            expected_output=(
                "Exactly 4 lines in the format:\n"
                "Option N: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale covering all destinations>"
            ),
        )

        return Crew(
            agents=[synthesizer],
            tasks=[task],
            process=Process.sequential,
            cache=True,
            task_callback=task_callback,
            verbose=True,
        )

    @staticmethod
    def destination_research_crew(task_callback=None) -> Crew:
        """Crew that researches a single destination.

        Designed for parallel execution via ``akickoff_for_each``.
        Task placeholders (supplied via the inputs dict):
            {destination_name}  – destination to research, e.g. "Tokyo"
            {pref_context}      – pre-formatted preferences & origin string
        """
        dest_expert = TravelAgents.destination_expert_agent()

        task = Task(
            description=(
                "Research {destination_name} and provide personalised recommendations.\n"
                "{pref_context}\n\n"
                "When calling tools, ALWAYS pass ALL available user preferences as arguments so\n"
                "search results are tailored rather than generic. Never leave preference fields blank.\n\n"
                "Tool-calling rules:\n"
                "1. research_destination — pass: destination={destination_name}, trip_theme,\n"
                "   budget_level, travel_group_type, travel_pace, origin_country, group_size.\n\n"
                "2. get_visa_requirements — pass: origin_country (traveller's passport country)\n"
                "   and destination_country={destination_name}. ALWAYS call this — visa info is essential.\n\n"
                "3. find_accommodations — pass: destination={destination_name}, budget_level,\n"
                "   trip_theme, travel_group_type, group_size, travel_pace.\n\n"
                "Cover must-see attractions, activities suited to the trip theme, local cuisine,\n"
                "transport options, and daily cost estimates. Include visa requirements.\n\n"
                "CRITICAL: All accommodation pricing MUST come from find_accommodations tool. "
                "If tool returns insufficient data, explicitly say INSUFFICIENT_DATA rather than "
                "estimating costs."
            ),
            agent=dest_expert,
            output_pydantic=DestinationResearchOutput,
            guardrail=_validate_destination_pricing_honesty,
            guardrail_max_retries=2,
            max_retry_limit=0,
            expected_output=(
                "Personalised destination guide for {destination_name} covering attractions, "
                "activities, dining, transport, budget, and visa info."
            ),
        )

        return Crew(
            agents=[dest_expert],
            tasks=[task],
            process=Process.sequential,
            cache=True,
            task_callback=task_callback,
            verbose=True,
        )

    @staticmethod
    def logistics_crew(context: str, task_callback=None) -> Crew:
        """Crew that creates a comprehensive day-by-day itinerary and logistics plan."""
        logistics_manager = TravelAgents.logistics_manager_agent()

        task = Task(
            description=(
                f"Create a comprehensive, day-by-day travel plan for: {context}\n\n"
                "When calling tools, ALWAYS pass ALL user preferences so results are tailored.\n"
                "Never leave preference fields blank.\n\n"
                "Tool-calling rules:\n"
                "1. plan_transportation — pass: start_location (origin city or origin_country),\n"
                "   end_location, duration_days, budget_level, travel_group_type, trip_theme,\n"
                "   origin_country, group_size.\n\n"
                "2. estimate_budget_breakdown — pass: destination, duration_days, budget_level,\n"
                "   group_size, trip_theme. ALWAYS use this tool for cost estimates.\n\n"
                "3. create_daily_itinerary — pass: destination, duration_days, trip_theme,\n"
                "   travel_pace, travel_group_type, budget_level. For multi-destination trips\n"
                "   call this tool ONCE PER destination (with that destination's day count).\n\n"
                "4. check_travel_insurance — pass: destination, trip_duration, budget_level,\n"
                "   origin_country.\n\n"
                "CRITICAL: Total budget estimates MUST come from estimate_budget_breakdown tool. "
                "If insufficient data, explicitly say INSUFFICIENT_DATA. Never guess costs.\n\n"
                "IMPORTANT for multi-destination trips: follow the Destination schedule in the\n"
                "context exactly. Label EVERY day heading with the real destination name:\n"
                "Day 1 — DestinationName\n"
                "- Morning: <activity>\n"
                "- Afternoon: <activity>\n"
                "- Evening: <activity>\n\n"
                "Day 2 — DestinationName\n"
                "...using the actual destination name (e.g. Paris, Tokyo) for EVERY day.\n\n"
                "Also include:\n"
                "- Estimated total budget with a $ figure (from estimate_budget_breakdown tool)\n"
                "- Key logistics: flights, visa requirements, recommended accommodation, insurance"
            ),
            agent=logistics_manager,
            output_pydantic=LogisticsOutput,
            guardrail=_validate_logistics_pacing,
            guardrail_max_retries=2,
            max_retry_limit=0,
            markdown=True,
            expected_output=(
                "Structured day-by-day itinerary (Day 1, Day 2, ...) with timed activities, "
                "a $ budget estimate (from estimate_budget_breakdown), and a key logistics section "
                "covering flights, visa, accommodation, and insurance."
            ),
        )

        return Crew(
            agents=[logistics_manager],
            tasks=[task],
            process=Process.sequential,
            cache=True,
            task_callback=task_callback,
            verbose=True,
        )
