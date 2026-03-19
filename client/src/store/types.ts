/**
 * Types for travel store.
 * These should match the Pydantic models from backend schema.py
 */

export interface DestinationInput {
  name: string;
  type: 'city' | 'country' | 'region' | 'landmark';
  priority: number;
}

export interface TravelPreferences {
  budget_level: 'budget' | 'moderate' | 'luxury';
  travel_pace: 'relaxed' | 'moderate' | 'fast';
  trip_theme?: string;
  travel_group_type: 'solo' | 'couple' | 'family' | 'friends';
  group_size: number;
  origin_country: string;
}

export interface FuzzyDateRange {
  rough_season?: string;
  rough_duration?: string;
  earliest_possible?: string;
  latest_possible?: string;
}

export interface ConfirmedDateRange {
  start_date: string;
  end_date: string;
  duration_days: number;
}

export interface ItineraryDay {
  day_number: number;
  date: string;
  title: string;
  activities: string[];
  notes?: string;
}

export interface Itinerary {
  trip_title: string;
  destinations: DestinationInput[];
  date_range: ConfirmedDateRange;
  days: ItineraryDay[];
  summary: string;
  estimated_budget?: string;
  key_logistics?: string[];
}

export interface TravelState {
  session_id: string;
  user_id?: string;
  rough_dates: FuzzyDateRange;
  destinations: DestinationInput[];
  preferences: TravelPreferences;
  confirmed_dates?: ConfirmedDateRange;
  itinerary?: Itinerary;
  ui_status:
    | 'pending'
    | 'researching'
    | 'awaiting_date_confirmation'
    | 'awaiting_itinerary_confirmation'
    | 'awaiting_user'
    | 'finalizing'
    | 'complete'
    | 'error';
  current_step: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
  agent_thoughts: string[];
}

export interface HumanFeedbackRequest {
  step: 'date_confirmation' | 'itinerary_review';
  message: string;
  options: string[];
  data: Record<string, unknown>;
  session_id: string;
}

/** A single date-range option proposed by the DateScout agent. */
export interface DateOption {
  start: string;          // ISO date string YYYY-MM-DD
  end: string;            // ISO date string YYYY-MM-DD
  duration_days: number;
  rationale: string;      // agent's explanation for why this window is good
}

export interface WebSocketMessage {
  type:
    | 'thought'
    | 'status_update'
    | 'itinerary_ready'
    | 'error'
    | 'state_sync'
    | 'human_feedback_requested'
    | 'flow_state_update'
    // CrewAI event types
    | 'crew_kickoff_started'
    | 'crew_kickoff_completed'
    | 'agent_execution_started'
    | 'agent_execution_completed'
    | 'task_started'
    | 'task_completed'
    | 'method_execution_started'
    | 'method_execution_finished'
    | 'flow_started'
    | 'flow_finished'
    | 'tool_usage_started'
    | 'tool_usage_finished'
    | string;
  data: Record<string, any>;
  timestamp: string;
}

export interface PlanInitializeRequest {
  rough_dates: FuzzyDateRange;
  destinations: DestinationInput[];
  preferences: TravelPreferences;
  user_id?: string;
  confirmed_dates?: ConfirmedDateRange;
}

export interface FeedbackSubmission {
  feedback_text: string;
  /** When the user chose a specific date option, include it here. */
  selected_dates?: {
    start_date: string;
    end_date: string;
    duration_days: number;
  };
}
