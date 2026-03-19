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
            max_iter=2,
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
            max_iter=2,
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
            max_iter=2,
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
    def date_scouting_crew(context: str) -> Crew:
        """Crew that analyses fuzzy dates and proposes concrete travel windows."""
        date_scout = TravelAgents.date_scout_agent()

        task = Task(
            description=(
                f"Analyse these travel date preferences and determine precise travel dates: {context}\n\n"
                "Use the available tools to look up real weather forecasts and upcoming events.\n"
                "Follow these rules when calling tools:\n\n"
                "1. analyze_fuzzy_dates — ALWAYS pass ALL date fields the user gave you:\n"
                "   - If the user specified exact dates (ISO format YYYY-MM-DD), pass them as\n"
                "     `earliest_date` and `latest_date` so queries are pinned to those months.\n"
                "   - If the user gave a rough season or rough duration, pass those as\n"
                "     `rough_season` and `rough_duration`.\n"
                "   - Pass the full destination name.\n\n"
                "2. check_travel_seasons — pass the destination AND the `timeframe` argument.\n"
                "   Build `timeframe` from whatever date info is available:\n"
                "   - Exact dates → format as 'Month YYYY' or 'MonthA–MonthB YYYY'\n"
                "   - Rough season + year → e.g. 'summer 2026'\n"
                "   - No dates → omit so the tool uses a sensible default.\n\n"
                "3. get_flight_availability — call with:\n"
                "   - `origin`: traveller's origin city if known, otherwise leave blank\n"
                "   - `origin_country`: traveller's home country (always pass this)\n"
                "   - `destination`: destination city/country\n"
                "   - `group_size`: number of travellers\n"
                "   - `budget_level`: traveller's budget level\n"
                "   - `travel_group_type`: type of travel group\n"
                "   - Exact ISO dates → pass as `start_date` / `end_date`.\n"
                "   - Only rough dates → pass the rough description string (e.g. 'June 2026').\n\n"
                "Derive the best recommended start and end dates solely from web research results.\n"
                "Factor in: weather conditions, crowd levels, local festivals, and any hard\n"
                "date bounds the user provided."
            ),
            agent=date_scout,
            expected_output=(
                "If rough/seasonal dates were given — EXACTLY 3–4 date range options:\n"
                "Option 1: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "Option 2: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "Option 3: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "Option 4: YYYY-MM-DD to YYYY-MM-DD (N days) - <rationale>\n"
                "If exact dates were given — a single confirmed range YYYY-MM-DD to YYYY-MM-DD "
                "with concise rationale grounded in real web research."
            ),
        )

        return Crew(
            agents=[date_scout],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

    @staticmethod
    def destination_research_crew(context: str) -> Crew:
        """Crew that researches destinations and provides personalised recommendations."""
        dest_expert = TravelAgents.destination_expert_agent()

        task = Task(
            description=(
                f"Research the following destinations and provide personalised recommendations: {context}\n\n"
                "When calling tools, ALWAYS pass ALL available user preferences as arguments so\n"
                "search results are tailored rather than generic. Never leave preference fields blank.\n\n"
                "Tool-calling rules:\n"
                "1. research_destination — pass: destination, trip_theme, budget_level,\n"
                "   travel_group_type, travel_pace, origin_country, group_size.\n\n"
                "2. get_visa_requirements — pass: origin_country (traveller's passport country)\n"
                "   and destination_country. ALWAYS call this tool — visa info is essential.\n\n"
                "3. find_accommodations — pass: destination, budget_level, trip_theme,\n"
                "   travel_group_type, group_size, travel_pace.\n\n"
                "Cover must-see attractions, activities suited to the trip theme, local cuisine,\n"
                "transport options, and daily cost estimates. Include visa requirements."
            ),
            agent=dest_expert,
            expected_output=(
                "Personalised destination guide covering attractions, activities, dining, "
                "transport, budget, and visa info."
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
                "   travel_pace, travel_group_type, budget_level.\n\n"
                "4. check_travel_insurance — pass: destination, trip_duration, budget_level,\n"
                "   origin_country.\n\n"
                "Structure your output EXACTLY like this for every day:\n"
                "Day 1 - <date or title>\n"
                "- Morning: <activity>\n"
                "- Afternoon: <activity>\n"
                "- Evening: <activity>\n\n"
                "Day 2 - <date or title>\n"
                "...and so on for every day.\n\n"
                "Also include:\n"
                "- Estimated total budget with a $ figure\n"
                "- Key logistics: flights, visa requirements, recommended accommodation, insurance"
            ),
            agent=logistics_manager,
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
