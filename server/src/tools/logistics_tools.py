"""Logistics planning tools for the LogisticsManager agent — powered by live web search"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
from crewai.tools import tool
from crewai_tools import SerperDevTool, ScrapeWebsiteTool

# Load .env from the server directory (two levels up from src/tools/)
load_dotenv(Path(__file__).parents[2] / ".env")

# ── Shared search + scrape instances ──────────────────────────────────
_serper: SerperDevTool | None = None
_scraper: ScrapeWebsiteTool | None = None


def _get_serper() -> SerperDevTool | None:
    global _serper
    if _serper is None:
        if not os.getenv("SERPER_API_KEY", ""):
            return None
        try:
            _serper = SerperDevTool(n_results=3)
        except Exception:
            return None
    return _serper


def _get_scraper() -> ScrapeWebsiteTool:
    global _scraper
    if _scraper is None:
        _scraper = ScrapeWebsiteTool()
    return _scraper


def _search_and_scrape(query: str, max_pages: int = 2) -> str:
    """Search with Serper, then scrape top URLs for full content."""
    serper = _get_serper()
    if serper is None:
        return "Search unavailable: SERPER_API_KEY not configured."

    try:
        raw = serper.run(search_query=query)
    except Exception as e:
        return f"Search failed: {e}"

    urls = []
    if isinstance(raw, dict):
        for item in raw.get("organic", []):
            link = item.get("link")
            if link:
                urls.append(link)
        for item in raw.get("news", []):
            link = item.get("link")
            if link:
                urls.append(link)

    if not urls:
        return json.dumps(raw) if isinstance(raw, dict) else str(raw)

    scraper = _get_scraper()
    scraped_content = []
    for url in urls[:max_pages]:
        try:
            content = scraper.run(website_url=url)
            if content and content.strip():
                scraped_content.append(f"--- Source: {url} ---\n{content[:3000]}")
        except Exception:
            continue

    if scraped_content:
        return "\n\n".join(scraped_content)

    return json.dumps(raw) if isinstance(raw, dict) else str(raw)


# ── Tool 1: Plan Transportation ─────────────────────────────────────────
@tool("plan_transportation")
def plan_transportation(
    start_location: str,
    end_location: str,
    duration_days: int,
    budget_level: Optional[str] = None,
    travel_group_type: Optional[str] = None,
    trip_theme: Optional[str] = None,
    origin_country: Optional[str] = None,
    group_size: int = 1,
) -> Dict[str, Any]:
    """
    Searches for flights and local transport options tailored to the traveler's
    budget, group type, group size, and origin country.

    Args:
        start_location: Origin city or country.
        end_location: Destination city or region.
        duration_days: Total trip duration in days.
        budget_level: "budget", "moderate", or "luxury".
        travel_group_type: e.g. "solo", "couple", "family", "friends".
        trip_theme: Trip theme (adventure, cultural, beach, etc.)
        origin_country: Traveler's home country — used to anchor flight search.
        group_size: Number of travelers.

    Returns:
        Flight options and local transportation tips.
    """
    # Use origin_country as fallback departure if start_location is vague
    departure = start_location
    if origin_country and start_location.lower() in ("", "unknown", "home"):
        departure = origin_country

    budget_str = f"{budget_level} " if budget_level else ""
    group_str = f"{travel_group_type} " if travel_group_type else ""
    pax_str = f"{group_size} passengers " if group_size > 1 else ""

    flights = _search_and_scrape(
        f"{budget_str}flights {departure} to {end_location} {pax_str}{group_str}traveler tips booking".strip()
    )
    local_transport = _search_and_scrape(
        f"best ways to get around {end_location} {budget_str}{group_str}transport guide".strip()
    )

    return {
        "route": f"{departure} → {end_location}",
        "duration": f"{duration_days} days",
        "budget_level": budget_level or "any",
        "travel_group_type": travel_group_type or "general",
        "group_size": group_size,
        "origin_country": origin_country or "not specified",
        "flight_options": flights,
        "local_transportation": local_transport,
    }


# ── Tool 2: Estimate Budget Breakdown ──────────────────────────────────
@tool("estimate_budget_breakdown")
def estimate_budget_breakdown(
    destination: str,
    duration_days: int,
    budget_level: str,
    group_size: int = 1,
    trip_theme: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Searches for real daily cost estimates tailored to destination, budget, and group.

    Args:
        destination: Destination name.
        duration_days: Trip duration in days.
        budget_level: "budget", "moderate", or "luxury".
        group_size: Number of travelers.
        trip_theme: Trip theme to refine activity cost estimates.

    Returns:
        Itemised real-world budget estimates.
    """
    theme_str = f"{trip_theme} " if trip_theme else ""
    group_str = f"group of {group_size} " if group_size > 1 else ""

    daily_costs = _search_and_scrape(
        f"{destination} daily travel cost {budget_level} traveler {group_str}"
        f"accommodation food {theme_str}activities breakdown".strip()
    )
    trip_total = _search_and_scrape(
        f"{duration_days} day trip {destination} total budget {budget_level} {group_str}estimate {theme_str}".strip()
    )

    return {
        "destination": destination,
        "duration": f"{duration_days} days",
        "group_size": group_size,
        "budget_level": budget_level,
        "daily_cost_breakdown": daily_costs,
        "total_trip_estimate": trip_total,
        "note": "Flight costs not included. Prices vary by season and availability.",
    }


# ── Tool 3: Create Daily Itinerary ─────────────────────────────────────
@tool("create_daily_itinerary")
def create_daily_itinerary(
    destination: str,
    duration_days: int,
    trip_theme: Optional[str] = None,
    travel_pace: Optional[str] = None,
    travel_group_type: Optional[str] = None,
    budget_level: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetches real day-by-day itinerary ideas tailored to the traveler's theme,
    pace, group type, and budget.

    Args:
        destination: Destination name.
        duration_days: Number of days.
        trip_theme: e.g. "adventure", "cultural", "beach", "romantic", "food".
        travel_pace: "relaxed", "moderate", or "fast".
        travel_group_type: e.g. "solo", "couple", "family", "friends".
        budget_level: "budget", "moderate", or "luxury".

    Returns:
        Curated day-by-day itinerary sourced from the web.
    """
    theme_str = f"{trip_theme} " if trip_theme else ""
    group_str = f"{travel_group_type} " if travel_group_type else ""
    pace_str = f"{travel_pace} pace " if travel_pace else ""
    budget_str = f"{budget_level} " if budget_level else ""

    itinerary = _search_and_scrape(
        f"{duration_days} day {theme_str}itinerary {destination} "
        f"{group_str}{pace_str}{budget_str}day by day guide".strip()
    )
    highlights = _search_and_scrape(
        f"top {theme_str}experiences {destination} {group_str}not to miss {budget_str}travel".strip()
    )

    return {
        "destination": destination,
        "duration": f"{duration_days} days",
        "theme": trip_theme or "flexible",
        "travel_pace": travel_pace or "moderate",
        "travel_group_type": travel_group_type or "general",
        "budget_level": budget_level or "moderate",
        "day_by_day_itinerary": itinerary,
        "must_do_highlights": highlights,
    }
    


# ── Tool 4: Check Travel Insurance ─────────────────────────────────────
@tool("check_travel_insurance")
def check_travel_insurance(
    destination: str,
    trip_duration: int,
    budget_level: Optional[str] = None,
    origin_country: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Searches for travel insurance options suitable for the destination, origin,
    trip duration, and budget.

    Args:
        destination: Destination country or region.
        trip_duration: Trip duration in days.
        budget_level: "budget", "moderate", or "luxury" — influences coverage tier.
        origin_country: Traveler's home country — used to find locally available policies.

    Returns:
        Travel insurance recommendations sourced from the web.
    """
    budget_str = f"{budget_level} " if budget_level else ""
    origin_str = f"for {origin_country} travelers " if origin_country else ""

    insurance = _search_and_scrape(
        f"best {budget_str}travel insurance {destination} {trip_duration} days "
        f"{origin_str}medical evacuation cancellation coverage comparison".strip()
    )

    return {
        "destination": destination,
        "trip_duration": f"{trip_duration} days",
        "budget_level": budget_level or "any",
        "origin_country": origin_country or "not specified",
        "insurance_recommendations": insurance,
        "disclaimer": (
            "Insurance policies vary. Compare multiple providers and read "
            "policy details carefully before purchasing."
        ),
    }
