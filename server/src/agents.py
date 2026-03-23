"""CrewAI Agent and Crew Definitions for Travel Planning"""

import os
from typing import Any, Tuple
from pydantic import BaseModel
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


# ---------------------------------------------------------------------------
# Task guardrails
# ---------------------------------------------------------------------------

def _validate_four_options(result) -> Tuple[bool, Any]:
    """Ensure the synthesis task returns exactly 4 date window options."""
    if result.pydantic and len(result.pydantic.options) == 4:
        return (True, result)
    return (False, "Must return exactly 4 date window options.")


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
        """
        return Agent(
            role="Fuzzy Date Analyst",
            goal=(
                "Parse vague or seasonal travel date inputs into concrete candidate date windows "
                "for {destination_name} using real data."
            ),
            backstory=(
                "You are an expert at decoding imprecise travel timelines like 'summer', "
                "'two weeks in autumn', or 'sometime in Q3'. You use analyze_fuzzy_dates to "
                "turn these descriptions into concrete date windows backed by real research."
            ),
            tools=[analyze_fuzzy_dates],
            llm=TravelAgents._get_llm("fast"),
            max_iter=5,
            inject_date=True,
            date_format="%Y-%m-%d",
            cache=True,
            respect_context_window=True,
            verbose=False,
        )

    @staticmethod
    def travel_season_analyst_agent() -> Agent:
        """
        Specialist: evaluates seasonal weather, crowd levels, and events for a destination.
        Sole tool: check_travel_seasons.
        """
        return Agent(
            role="Travel Season Analyst",
            goal=(
                "Research seasonal weather, crowd levels, and events for {destination_name} "
                "in the relevant travel window."
            ),
            backstory=(
                "You are a destination climate and events specialist who knows peak, shoulder, "
                "and off-season windows for destinations worldwide. You use check_travel_seasons "
                "to fetch accurate, up-to-date seasonal intelligence."
            ),
            tools=[check_travel_seasons],
            llm=TravelAgents._get_llm("fast"),
            max_iter=5,
            inject_date=True,
            date_format="%Y-%m-%d",
            cache=True,
            respect_context_window=True,
            verbose=False,
        )

    @staticmethod
    def flight_scout_agent() -> Agent:
        """
        Specialist: researches flight availability, pricing, and booking tips.
        Sole tool: get_flight_availability.
        """
        return Agent(
            role="Flight Scout",
            goal=(
                "Research flight availability, price ranges, and booking advice for "
                "travel to {destination_name}."
            ),
            backstory=(
                "You are a flights and routing specialist who knows what routes exist, "
                "when to book, and what prices travellers should expect. You use "
                "get_flight_availability and always pass all traveller context so results "
                "are personalised."
            ),
            tools=[get_flight_availability],
            llm=TravelAgents._get_llm("fast"),
            max_iter=5,
            cache=True,
            respect_context_window=True,
            verbose=False,
        )

    @staticmethod
    def date_scout_manager_agent() -> Agent:
        """
        Manager: orchestrates the three date-scouting specialists and synthesises
        their findings into a concise date-scouting report. No tools — pure reasoning.
        """
        return Agent(
            role="Date Scout Manager",
            goal=(
                "Delegate date-research work to the right specialists, then synthesise their "
                "findings into a concise, well-structured date-scouting report for "
                "{destination_name}."
            ),
            backstory=(
                "You are a senior travel research manager who leads a team of date-scouting "
                "specialists. You direct your Fuzzy Date Analyst, Travel Season Analyst, and "
                "Flight Scout to each do their focused research, then you combine their outputs "
                "into a clear summary that the downstream planning stages can use directly."
            ),
            tools=[],  # orchestrator only — no direct tool calls
            llm=TravelAgents._get_llm("reasoning"),
            max_iter=10,
            inject_date=True,
            date_format="%Y-%m-%d",
            respect_context_window=True,
            verbose=False,
        )

    @staticmethod
    def destination_expert_agent() -> Agent:
        """
        DestExpert agent: Specialized in destination research and recommendations.
        """
        return Agent(
            role="Destination Expert",
            goal="Research destinations thoroughly and provide personalized travel recommendations",
            backstory="""You are a seasoned travel consultant who has visited hundreds of destinations.
            You know the hidden gems, the best activities, visa requirements, cuisine, culture, and logistics
            for destinations around the world. You tailor recommendations based on travel style and preferences.""",
            tools=[
                research_destination,
                get_visa_requirements,
                find_accommodations,
            ],
            llm=TravelAgents._get_llm("standard"),
            max_iter=5,
            cache=True,
            respect_context_window=True,
            verbose=False,
        )

    @staticmethod
    def logistics_manager_agent() -> Agent:
        """
        LogisticsManager agent: Specialized in planning trip logistics and itineraries.
        """
        return Agent(
            role="Logistics Manager",
            goal="Create comprehensive travel logistics and day-by-day itineraries that maximize experiences within constraints",
            backstory="""You are a masterful trip planner who excels at optimizing travel logistics, budgets,
            and itineraries. You understand transportation, accommodation, budgeting, and can create detailed
            daily plans that balance activities, rest, and practical considerations. You always prioritize
            traveler comfort and safety.""",
            tools=[
                plan_transportation,
                estimate_budget_breakdown,
                create_daily_itinerary,
                check_travel_insurance,
            ],
            llm=TravelAgents._get_llm("standard"),
            max_iter=5,
            cache=True,
            respect_context_window=True,
            verbose=False,
        )

    @staticmethod
    def date_synthesizer_agent() -> Agent:
        """
        DateSynthesizer agent: Combines per-destination date analysis results into
        exactly 4 travel windows that work for ALL destinations simultaneously.
        No tools — it reasons purely over the provided context.
        """
        return Agent(
            role="Date Synthesizer",
            goal=(
                "Analyse the date research reports for multiple destinations and produce "
                "exactly 4 concrete travel date windows that are simultaneously ideal for "
                "every destination. Each window must match the user's requested trip duration "
                "and include a rationale that mentions every destination by name."
            ),
            backstory=(
                "You are a senior travel strategist who specialises in multi-destination trip "
                "planning. You read per-destination seasonal research and identify the windows "
                "of time where weather, events, and crowds align well across all locations at once. "
                "You are precise with dates and always justify each suggestion clearly."
            ),
            tools=[],  # Pure reasoning — no tool calls needed
            llm=TravelAgents._get_llm("reasoning"),
            max_iter=5,
            inject_date=True,
            date_format="%Y-%m-%d",
            respect_context_window=True,
            verbose=False,
        )

    @staticmethod
    def trip_interpreter_agent() -> Agent:
        """
        TripInterpreter agent: parses the user's natural-language description and
        preferences into a structured, richly-detailed trip outline.
        No tools — pure reasoning over the provided context.
        """
        return Agent(
            role="Trip Interpreter",
            goal=(
                "Read the traveller\'s own words and stated preferences, then produce a clear, "
                "structured outline of what this trip should look and feel like: the vibe, "
                "key experiences, estimated pace per destination, and any implicit needs "
                "(accessibility, dietary, etc.). This outline will guide every downstream "
                "planning step."
            ),
            backstory=(
                "You are a master travel consultant who excels at translating vague travel "
                "dreams into concrete, actionable trip blueprints. You read between the lines "
                "of a traveller\'s description — picking up on tone, priorities, and unstated "
                "expectations — and produce structured outlines that set the other planning "
                "agents up for success."
            ),
            tools=[],
            llm=TravelAgents._get_llm("standard"),
            max_iter=3,
            inject_date=True,
            date_format="%Y-%m-%d",
            respect_context_window=True,
            verbose=False,
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
                "Produce a detailed, structured trip outline with the following sections:\n"
                "1. Trip Vibe & Theme — the overall feel and purpose of the trip (2–3 sentences).\n"
                "2. Destinations & Highlights — for each destination: key experiences, "
                "must-do activities, and estimated days appropriate given the pace/budget.\n"
                "3. Implicit Needs — anything the traveller has implied but not stated "
                "(dietary preferences, accessibility needs, photography spots, family-friendliness, "
                "romance-focused experiences, night-life expectations, etc.).\n"
                "4. Ideal Date Constraints — the season, weather, or event windows that would "
                "make this trip exceptional for these specific destinations and interests.\n"
                "5. Budget Sense-check — whether the stated budget is realistic for the "
                "destinations, group size, and pace described, and any notable caveats.\n\n"
                "Be specific and opinionated. This outline is used by every downstream agent — "
                "date scouts, destination researchers, and logistics planners — so the more "
                "concrete and tailored the better."
            ),
            agent=interpreter,
            max_retry_limit=0,
            markdown=True,
            expected_output=(
                "Structured trip outline with five clearly-labelled sections: "
                "Trip Vibe & Theme, Destinations & Highlights, Implicit Needs, "
                "Ideal Date Constraints, and Budget Sense-check."
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
                "Report available routes, rough price ranges, and booking recommendations."
            ),
            agent=flight_scout,
            max_retry_limit=0,
            expected_output=(
                "Flight summary for {destination_name}: route options, price ranges, and "
                "booking tips tailored to the traveller profile."
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
                "transport options, and daily cost estimates. Include visa requirements."
            ),
            agent=dest_expert,
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
                "   group_size, trip_theme.\n\n"
                "3. create_daily_itinerary — pass: destination, duration_days, trip_theme,\n"
                "   travel_pace, travel_group_type, budget_level. For multi-destination trips\n"
                "   call this tool ONCE PER destination (with that destination's day count).\n\n"
                "4. check_travel_insurance — pass: destination, trip_duration, budget_level,\n"
                "   origin_country.\n\n"
                "IMPORTANT for multi-destination trips: follow the Destination schedule in the\n"
                "context exactly. Label EVERY day heading with the real destination name:\n"
                "Day 1 — DestinationName\n"
                "- Morning: <activity>\n"
                "- Afternoon: <activity>\n"
                "- Evening: <activity>\n\n"
                "Day 2 — DestinationName\n"
                "...using the actual destination name (e.g. Paris, Tokyo) for EVERY day.\n\n"
                "Also include:\n"
                "- Estimated total budget with a $ figure\n"
                "- Key logistics: flights, visa requirements, recommended accommodation, insurance"
            ),
            agent=logistics_manager,
            max_retry_limit=0,
            markdown=True,
            expected_output=(
                "Structured day-by-day itinerary (Day 1, Day 2, ...) with timed activities, "
                "a $ budget estimate, and a key logistics section covering flights, visa, "
                "accommodation, and insurance."
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
