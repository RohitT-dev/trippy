"""Destination research tools for the DestExpert agent — powered by live web search"""

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


def _search(query: str, max_pages: int = 2) -> str:
    return _search_and_scrape(query, max_pages)


# ── Tool 1: Research Destination ──────────────────────────────────────
@tool("research_destination")
def research_destination(
    destination: str,
    trip_theme: Optional[str] = None,
    budget_level: Optional[str] = None,
    travel_group_type: Optional[str] = None,
    travel_pace: Optional[str] = None,
    origin_country: Optional[str] = None,
    group_size: int = 1,
) -> Dict[str, Any]:
    """
    Researches a destination using live web search, tailored to the traveler's
    preferences — theme, budget, group type, pace, group size, and origin country.

    Args:
        destination: Name of the destination (city or country).
        trip_theme: e.g. "adventure", "cultural", "beach", "food", "romantic".
        budget_level: "budget", "moderate", or "luxury".
        travel_group_type: e.g. "solo", "couple", "family", "friends".
        travel_pace: "relaxed", "moderate", or "fast".
        origin_country: Traveler's home country — used to tailor practical tips.
        group_size: Number of travelers.

    Returns:
        Personalised destination research from the web.
    """
    theme_str = f"{trip_theme} " if trip_theme else ""
    group_str = f"for {travel_group_type} traveler " if travel_group_type else ""
    budget_str = f"{budget_level} budget " if budget_level else ""
    pace_str = f"{travel_pace} pace " if travel_pace else ""
    pax_str = f"group of {group_size} " if group_size > 1 else ""
    origin_str = f"from {origin_country} " if origin_country else ""
    context = f"{theme_str}{group_str}{pax_str}{budget_str}{pace_str}".strip()

    attractions = _search(
        f"{destination} top attractions {context}".strip()
    )
    activities = _search(
        f"{destination} best {theme_str}activities things to do {group_str}{pax_str}".strip()
    )
    cuisine = _search(
        f"{destination} {budget_str}restaurants local food must-try dishes".strip()
    )
    transport = _search(
        f"{destination} getting around transport tips {group_str}{origin_str}".strip()
    )
    budget = _search(
        f"{destination} daily travel cost {budget_str}{pax_str}".strip()
    )

    return {
        "destination": destination,
        "preferences_used": {
            "trip_theme": trip_theme,
            "budget_level": budget_level,
            "travel_group_type": travel_group_type,
            "travel_pace": travel_pace,
            "origin_country": origin_country,
            "group_size": group_size,
        },
        "must_see_attractions": attractions,
        "activities_and_experiences": activities,
        "cuisine_and_dining": cuisine,
        "transport_and_getting_around": transport,
        "daily_budget_estimate": budget,
    }


# ── Tool 2: Visa Requirements ────────────────────────────────────────
@tool("get_visa_requirements")
def get_visa_requirements(
    origin_country: str,
    destination_country: str,
) -> Dict[str, Any]:
    """
    Searches the web for current visa requirements between two countries.

    Args:
        origin_country: Traveler's nationality / passport country.
        destination_country: Country being visited.

    Returns:
        Visa requirement details sourced from the web.
    """
    visa_info = _search(
        f"{origin_country} passport visa requirements "
        f"to travel to {destination_country} 2025 2026"
    )
    processing = _search(
        f"{destination_country} visa processing time "
        f"and application steps for {origin_country} citizens"
    )
    embassy = _search(
        f"{destination_country} embassy consulate website "
        f"visa application for {origin_country} nationals"
    )

    return {
        "from": origin_country,
        "to": destination_country,
        "visa_requirements": visa_info,
        "processing_and_steps": processing,
        "official_sources": embassy,
        "disclaimer": (
            "Visa policies change frequently. Always verify with the "
            "official embassy or consulate before booking travel."
        ),
    }


# ── Tool 3: Find Accommodations ──────────────────────────────────────
@tool("find_accommodations")
def find_accommodations(
    destination: str,
    budget_level: str,
    trip_theme: Optional[str] = None,
    travel_group_type: Optional[str] = None,
    group_size: int = 1,
    travel_pace: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Searches the web for real accommodation options matching
    the traveler's budget, group type, trip style, and group size.

    Args:
        destination: Destination name (city or region).
        budget_level: "budget", "moderate", or "luxury".
        trip_theme: Optional theme — e.g. "adventure", "romantic",
                    "cultural", "beach", "family".
        travel_group_type: e.g. "solo", "couple", "family", "friends".
        group_size: Number of travelers — important for room/suite sizing.
        travel_pace: "relaxed", "moderate", or "fast" — affects location preference.

    Returns:
        Accommodation suggestions sourced from the web.
    """
    theme_str = f"{trip_theme} " if trip_theme else ""
    group_str = f"{travel_group_type} " if travel_group_type else ""
    pax_str = f"{group_size} guests " if group_size > 1 else ""
    pace_str = f"{travel_pace} pace " if travel_pace else ""

    accommodations = _search(
        f"best {budget_level} {theme_str}hotels accommodations in {destination} "
        f"for {pax_str}{group_str}travelers recommendations".strip()
    )
    neighborhoods = _search(
        f"best area to stay in {destination} {budget_level} {group_str}{theme_str}{pace_str}trip".strip()
    )

    return {
        "destination": destination,
        "budget_level": budget_level,
        "trip_theme": trip_theme or "general",
        "travel_group_type": travel_group_type or "general",
        "group_size": group_size,
        "travel_pace": travel_pace or "moderate",
        "accommodation_results": accommodations,
        "best_neighborhoods": neighborhoods,
    }
