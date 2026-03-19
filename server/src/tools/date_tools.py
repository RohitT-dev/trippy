"""Date scouting tools for the DateScout agent — powered by real web search"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from crewai.tools import tool
from crewai_tools import SerperDevTool, ScrapeWebsiteTool

# Load .env from the server directory (one level up from src/tools/)
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


def _search_web(query: str) -> str:
    return _search_and_scrape(query)


def _search_news(query: str) -> str:
    return _search_and_scrape(query)


# ── Tool 1: Analyze Fuzzy Dates ──────────────────────────────────────
@tool("analyze_fuzzy_dates")
def analyze_fuzzy_dates(
    destination: str,
    rough_season: Optional[str] = None,
    rough_duration: Optional[str] = None,
    earliest_date: Optional[str] = None,
    latest_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyzes fuzzy/approximate date inputs, enriches them with real web data
    about the destination's climate and events, and returns precise date ranges.

    Args:
        destination: The travel destination (used to look up real season info).
        rough_season: e.g. "summer", "late spring", "monsoon season"
        rough_duration: e.g. "2 weeks", "10 days", "3-4 weeks"
        earliest_date: ISO date string — hard lower bound
        latest_date: ISO date string — hard upper bound

    Returns:
        Dictionary with web research and the user-supplied date constraints.
    """
    current_year = datetime.utcnow().year

    # ── Build a precise date context from whatever the user gave us ──
    date_parts: list[str] = []
    if earliest_date and latest_date:
        try:
            start = datetime.fromisoformat(earliest_date)
            end   = datetime.fromisoformat(latest_date)
            # e.g. "June–July 2026" or "June 2026" when same month
            if start.year == end.year and start.month == end.month:
                date_parts.append(start.strftime("%B %Y"))
            else:
                date_parts.append(
                    f"{start.strftime('%B')}–{end.strftime('%B %Y')}"
                )
        except ValueError:
            date_parts.append(f"{earliest_date} to {latest_date}")
    elif earliest_date:
        try:
            start = datetime.fromisoformat(earliest_date)
            date_parts.append(start.strftime("%B %Y"))
        except ValueError:
            date_parts.append(earliest_date)
    elif latest_date:
        try:
            end = datetime.fromisoformat(latest_date)
            date_parts.append(end.strftime("%B %Y"))
        except ValueError:
            date_parts.append(latest_date)

    if rough_season:
        date_parts.append(rough_season)
    if not date_parts:
        date_parts.append(str(current_year))

    date_ctx = " ".join(date_parts)  # e.g. "June–July 2026 late spring"

    # ── Queries anchored to the concrete date window ─────────────────
    season_query = (
        f"best time to visit {destination} in {date_ctx} "
        f"weather climate conditions"
    )
    web_research = _search_web(season_query)

    duration_hint = f"for {rough_duration}" if rough_duration else ""
    events_query = (
        f"{destination} events festivals {date_ctx} {duration_hint} "
        f"what to do"
    ).strip()
    events_research = _search_news(events_query)

    return {
        "destination": destination,
        "date_context": date_ctx,
        "rough_season": rough_season or "flexible",
        "rough_duration": rough_duration or "flexible",
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "web_research_best_time": web_research,
        "upcoming_events_news": events_research,
    }


# ── Tool 2: Check Travel Seasons ─────────────────────────────────────
@tool("check_travel_seasons")
def check_travel_seasons(destination: str, timeframe: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches forecasted or historical weather conditions for a destination
    during a given timeframe to help determine the best travel window.

    Args:
        destination: Name of the destination (city or country).
        timeframe: Optional travel window, e.g. "April 2026", "June–July 2026",
                   or a rough description like "summer 2026".

    Returns:
        Weather forecast and conditions sourced from the web.
    """
    # Use the supplied timeframe, or fall back to next month as a sensible default
    if timeframe:
        period = timeframe
    else:
        next_month = datetime.utcnow().replace(day=1) + timedelta(days=32)
        period = next_month.strftime("%B %Y")

    weather_results = _search_and_scrape(
        f"{destination} weather forecast {period} temperature rain conditions what to expect"
    )

    return {
        "destination": destination,
        "timeframe": period,
        "weather_forecast": weather_results,
    }


# ── Tool 3: Get Flight Availability ──────────────────────────────────
@tool("get_flight_availability")
def get_flight_availability(
    origin: str,
    destination: str,
    start_date: str,
    end_date: str,
    origin_country: Optional[str] = None,
    travel_group_type: Optional[str] = None,
    group_size: int = 1,
    budget_level: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Searches the web for real flight pricing trends and availability
    between two cities for the given date range.

    Args:
        origin: Origin city or airport (falls back to origin_country if blank).
        destination: Destination city or airport code.
        start_date: ISO format departure date (YYYY-MM-DD) or rough description
                    like "June 2026" if exact dates are not yet known.
        end_date: ISO format return date (YYYY-MM-DD) or rough description.
        origin_country: Traveler's home country — used for broader route queries.
        travel_group_type: e.g. "solo", "couple", "family", "friends".
        group_size: Number of travelers.
        budget_level: "budget", "moderate", or "luxury".

    Returns:
        Flight availability insights from web search results.
    """
    # Fall back to origin_country when origin city is not known
    departure = origin if origin and origin.lower() not in ("", "unknown") else (origin_country or origin)

    # ── Humanize date strings for better search results ───────────────
    def _humanize(date_str: str) -> str:
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            return date_str

    human_start = _humanize(start_date)
    human_end   = _humanize(end_date)

    # Derive month range label (e.g. "June–July 2026") for broader queries
    try:
        s = datetime.fromisoformat(start_date)
        e = datetime.fromisoformat(end_date)
        if s.year == e.year and s.month == e.month:
            month_range = s.strftime("%B %Y")
        else:
            month_range = f"{s.strftime('%B')}–{e.strftime('%B %Y')}"
    except (ValueError, TypeError):
        month_range = f"{start_date} to {end_date}"

    budget_str = f"{budget_level} " if budget_level else ""
    group_str  = f"{travel_group_type} " if travel_group_type else ""
    pax_str    = f"{group_size} passengers " if group_size > 1 else ""

    # ── Price / availability search ───────────────────────────────────
    flight_query = (
        f"{budget_str}flights from {departure} to {destination} "
        f"departing {human_start} returning {human_end} "
        f"{pax_str}price estimate cheapest options"
    ).strip()
    flight_results = _search_web(flight_query)

    # ── Booking tips anchored to travel month ─────────────────────────
    tips_query = (
        f"cheapest way to fly {departure} to {destination} "
        f"in {month_range} {budget_str}{group_str}booking tips best airline advance purchase"
    ).strip()
    tips_results = _search_web(tips_query)

    # ── Airline deals for that period ─────────────────────────────────
    deals_results = _search_news(
        f"flight deals {departure} {destination} {month_range} sale discount"
    )

    return {
        "route": f"{departure} → {destination}",
        "travel_dates": f"{human_start} to {human_end}",
        "month_range": month_range,
        "budget_level": budget_level or "any",
        "group_size": group_size,
        "flight_search_results": flight_results,
        "booking_tips": tips_results,
        "recent_deals_news": deals_results,
    }