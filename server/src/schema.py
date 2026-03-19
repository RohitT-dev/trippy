"""
Pydantic models shared between frontend and backend.
These models define the shape of data flowing through the CrewAI Flow and API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.flow.flow import FlowState


class DestinationInput(BaseModel):
    """User's destination preference"""
    name: str = Field(..., description="Destination name (e.g., 'Tokyo', 'Bali')")
    type: str = Field(
        default="city",
        description="Type: city, country, region, or landmark"
    )
    priority: int = Field(
        default=1,
        description="Priority ranking (1=highest)"
    )


class TravelPreferences(BaseModel):
    """Budgeting and experience preferences"""
    budget_level: str = Field(
        default="moderate",
        description="Budget: budget, moderate, luxury"
    )
    travel_pace: str = Field(
        default="moderate",
        description="Pace: relaxed, moderate, fast"
    )
    trip_theme: Optional[str] = Field(
        default=None,
        description="Trip theme: adventure, cultural, beach, mountains, food, etc."
    )
    travel_group_type: str = Field(
        default="solo",
        description="Who's traveling: solo, couple, family, friends"
    )
    group_size: int = Field(
        default=1,
        description="Number of travelers in the group"
    )
    origin_country: str = Field(
        default="",
        description="Country the traveler is departing from (nationality/passport country)"
    )


class FuzzyDateRange(BaseModel):
    """Fuzzy date inputs from user (not precise dates)"""
    rough_season: Optional[str] = Field(
        default=None,
        description="e.g., 'summer', 'winter', 'late spring'"
    )
    rough_duration: Optional[str] = Field(
        default=None,
        description="e.g., '2 weeks', '10 days', '3-4 weeks'"
    )
    earliest_possible: Optional[datetime] = Field(
        default=None,
        description="Earliest possible start date if specified"
    )
    latest_possible: Optional[datetime] = Field(
        default=None,
        description="Latest possible end date if specified"
    )


class ConfirmedDateRange(BaseModel):
    """Precise dates confirmed by user after agent refinement"""
    start_date: datetime
    end_date: datetime
    duration_days: int


class ItineraryDay(BaseModel):
    """Single day's itinerary"""
    day_number: int
    date: datetime
    title: str
    activities: List[str]
    notes: Optional[str] = None


class Itinerary(BaseModel):
    """Complete itinerary with day-by-day breakdown"""
    trip_title: str
    destinations: List[DestinationInput]
    date_range: ConfirmedDateRange
    days: List[ItineraryDay]
    summary: str
    estimated_budget: Optional[str] = None
    key_logistics: List[str] = Field(
        default_factory=list,
        description="Flights, visas, accommodations, etc."
    )


class TravelState(FlowState):
    """
    Core state machine for the travel planning flow.
    Inherits FlowState for automatic `id` management and Flow[T] compatibility.
    Shared between CrewAI Flows backend and frontend Zustand store.
    """
    session_id: str = Field(..., description="Unique session identifier")
    user_id: Optional[str] = Field(default=None, description="User identifier for personalization")

    # User Inputs
    rough_dates: FuzzyDateRange = Field(
        default_factory=FuzzyDateRange,
        description="User's fuzzy/approximate travel dates"
    )
    destinations: List[DestinationInput] = Field(
        default_factory=list,
        description="List of destinations user wants to visit"
    )
    preferences: TravelPreferences = Field(
        default_factory=TravelPreferences,
        description="User's travel preferences"
    )

    # Refined by Agents
    confirmed_dates: Optional[ConfirmedDateRange] = Field(
        default=None,
        description="Precise dates refined by DateScout agent"
    )
    proposed_date_options: List[ConfirmedDateRange] = Field(
        default_factory=list,
        description="3–4 date window options proposed by DateScout when rough/seasonal dates are given"
    )
    agent_outputs: Dict[str, str] = Field(
        default_factory=dict,
        description="Raw text outputs from each agent step, keyed by step name"
    )

    # Final Output
    itinerary: Optional[Itinerary] = Field(
        default=None,
        description="Final trip itinerary"
    )

    # UI State
    ui_status: str = Field(
        default="pending",
        description="Current status: pending, researching, awaiting_user, finalizing, complete, error"
    )
    current_step: str = Field(
        default="gathering_inputs",
        description="Current step in flow"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if something went wrong"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    agent_thoughts: List[str] = Field(
        default_factory=list,
        description="Agent thought stream for UI"
    )


class WebSocketMessage(BaseModel):
    """Message format for WebSocket communication"""
    type: str = Field(..., description="Message type: thought, status_update, itinerary_ready, error")
    data: Dict[str, Any] = Field(default_factory=dict, description="Message payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PlanInitializeRequest(BaseModel):
    """Request to initialize travel planning flow"""
    rough_dates: FuzzyDateRange
    destinations: List[DestinationInput]
    preferences: Optional[TravelPreferences] = Field(default_factory=TravelPreferences)
    user_id: Optional[str] = None
    confirmed_dates: Optional[ConfirmedDateRange] = Field(
        default=None,
        description="Exact dates if the user already knows their travel window"
    )


class PlanConfirmRequest(BaseModel):
    """Request to confirm refined dates"""
    session_id: str
    confirmed_dates: ConfirmedDateRange


class SessionResponse(BaseModel):
    """Response with session details"""
    session_id: str
    state: TravelState


class FeedbackSubmission(BaseModel):
    """Body for POST /api/plan/{session_id}/feedback"""
    feedback_text: str = Field(
        ...,
        description="Free-form text the user entered; mapped to an emit outcome by the LLM.",
    )
    selected_dates: Optional[ConfirmedDateRange] = Field(
        default=None,
        description="When the user chose a specific date option, pass it here so the "
                    "backend can update confirmed_dates before unblocking the flow thread.",
    )
