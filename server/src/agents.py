"""CrewAI Agent and Crew Definitions for Travel Planning"""

import os
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


class TravelAgents:
    """Collection of agents for travel planning"""

    @staticmethod
    def _get_llm():
        """Get configured LLM based on environment settings"""
        llm_provider = os.getenv("LLM_PROVIDER", "ollama")
        
        if llm_provider == "ollama":
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            model = os.getenv("OLLAMA_MODEL", "ministral-3:8b")
            return LLM(
                model=f"ollama/{model}",
                base_url=base_url
            )
        else:
            # Default to OpenAI if specified
            return None  # CrewAI will use default OpenAI

    @staticmethod
    def date_scout_agent() -> Agent:
        """
        DateScout agent: Specialized in parsing fuzzy dates and finding optimal travel windows.
        """
        return Agent(
            role="Date Scout",
            goal="Analyze fuzzy travel dates and convert them to precise date ranges that work for the user's needs",
            backstory="""You are an expert in understanding vague travel timelines and converting them into
            concrete dates. You know how to work with seasons, durations, and constraints to find the best
            possible travel window. You consider weather patterns, seasonal events, and crowd levels.""",
            tools=[
                analyze_fuzzy_dates,
                check_travel_seasons,
                get_flight_availability
            ],
            llm=TravelAgents._get_llm(),
            max_iter=1,
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
            llm=TravelAgents._get_llm(),
            max_iter=1,
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
            llm=TravelAgents._get_llm(),
            max_iter=1,
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
            llm=TravelAgents._get_llm(),
            max_iter=1,
            verbose=False,
        )



# ---------------------------------------------------------------------------
# Crew factories — one per planning stage
# ---------------------------------------------------------------------------

class TravelCrews:
    """Factory for travel-planning Crews.

    Each method assembles the relevant Agents, Tasks, and a Crew for one
    planning stage.  To extend a stage, instantiate additional agents here,
    create their Tasks, and add them to the ``agents`` / ``tasks`` lists
    before constructing the Crew.
    """

    @staticmethod
    def date_scouting_crew() -> Crew:
        """Crew that analyses fuzzy dates and proposes concrete travel windows.

        Designed for parallel execution via ``akickoff_for_each``.
        Task placeholders (supplied via the inputs dict):
            {destination_name}     – single destination to research, e.g. "Tokyo"
            {date_ctx}             – pre-formatted date context string
            {pref_context}         – pre-formatted preferences & origin string
            {is_rough_instruction} – empty string for exact dates; the
                                     "IMPORTANT: return 3–4 options…" block for rough dates
        """
        date_scout = TravelAgents.date_scout_agent()

        task = Task(
            description=(
                "Analyse travel dates for {destination_name} and determine the best concrete "
                "travel window.\n\n"
                "Date context: {date_ctx}\n"
                "{pref_context}\n\n"
                "Use the available tools to look up real weather forecasts and upcoming events "
                "for {destination_name}.\n"
                "Follow these rules when calling tools:\n\n"
                "1. analyze_fuzzy_dates — pass:\n"
                "   - destination = {destination_name}\n"
                "   - All date fields present in the date context above:\n"
                "     exact ISO dates → earliest_date / latest_date\n"
                "     rough season / duration → rough_season / rough_duration\n\n"
                "2. check_travel_seasons — pass:\n"
                "   - destination = {destination_name}\n"
                "   - timeframe built from the date context above\n"
                "     (e.g. 'June 2026', 'summer 2026', 'Jun–Jul 2026')\n\n"
                "3. get_flight_availability — pass:\n"
                "   - destination = {destination_name}\n"
                "   - All fields from {pref_context} (origin_country, group_size, "
                "budget_level, travel_group_type)\n"
                "   - Exact ISO dates → start_date / end_date; rough dates → date description\n\n"
                "Derive the best recommended start and end dates solely from web research results.\n"
                "Factor in: weather conditions, crowd levels, local festivals, and any hard "
                "date bounds provided.\n\n"
                "{is_rough_instruction}"
            ),
            agent=date_scout,
            max_retry_limit=0,
            expected_output=(
                "If rough/seasonal dates were given — EXACTLY 3–4 date range options for "
                "{destination_name}:\n"
                "Option 1: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "Option 2: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "Option 3: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "Option 4: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "If exact dates were given — a single confirmed range YYYY-MM-DD to YYYY-MM-DD "
                "with concise rationale grounded in real web research for {destination_name}."
            ),
        )

        return Crew(
            agents=[date_scout],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

    @staticmethod
    def date_synthesis_crew(context: str) -> Crew:
        """Crew that synthesises per-destination date-scouting results into
        4 combined travel windows suitable for ALL destinations.

        Args:
            context: Pre-formatted string containing per-destination raw outputs,
                     user preferences, requested duration, and destination list.
        """
        synthesizer = TravelAgents.date_synthesizer_agent()

        task = Task(
            description=(
                f"{context}\n\n"
                "Your task:\n"
                "Read the per-destination date reports above carefully. "
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
            max_retry_limit=0,
            expected_output=(
                "Exactly 4 lines in the format:\n"
                "Option N: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale covering all destinations>"
            ),
        )

        return Crew(
            agents=[synthesizer],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

    @staticmethod
    def destination_research_crew() -> Crew:
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
            verbose=True,
        )

    @staticmethod
    def logistics_crew(context: str) -> Crew:
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
            verbose=True,
        )
