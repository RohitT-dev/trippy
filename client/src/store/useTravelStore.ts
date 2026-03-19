/**
 * useTravelStore - Zustand store for travel planning state management
 * Manages TravelState and actions for updating it
 */

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import {
  TravelState,
  DestinationInput,
  TravelPreferences,
  FuzzyDateRange,
  ConfirmedDateRange,
  Itinerary,
  HumanFeedbackRequest,
} from './types';

const DEFAULT_PREFERENCES: TravelPreferences = {
  budget_level: 'moderate',
  travel_pace: 'moderate',
  trip_theme: undefined,
  travel_group_type: 'solo',
  group_size: 1,
  origin_country: '',
};

interface TravelStore extends TravelState {
  // Human-feedback overlay
  pendingFeedback: HumanFeedbackRequest | null;
  // Actions
  setSessionId: (id: string) => void;
  setUserId: (id: string) => void;
  setRoughDates: (dates: FuzzyDateRange) => void;
  setDestinations: (destinations: DestinationInput[]) => void;
  addDestination: (destination: DestinationInput) => void;
  removeDestination: (name: string) => void;
  setPreferences: (prefs: TravelPreferences) => void;
  setConfirmedDates: (dates: ConfirmedDateRange) => void;
  setItinerary: (itinerary: Itinerary) => void;
  setUIStatus: (status: TravelState['ui_status']) => void;
  setCurrentStep: (step: string) => void;
  setErrorMessage: (error: string | null) => void;
  addThought: (thought: string) => void;
  clearThoughts: () => void;
  loadState: (state: TravelState) => void;
  setPendingFeedback: (req: HumanFeedbackRequest | null) => void;
  reset: () => void;
}

const createInitialState = (): TravelState => ({
  session_id: '',
  user_id: undefined,
  rough_dates: {
    rough_season: undefined,
    rough_duration: undefined,
    earliest_possible: undefined,
    latest_possible: undefined,
  },
  destinations: [],
  preferences: DEFAULT_PREFERENCES,
  confirmed_dates: undefined,
  itinerary: undefined,
  ui_status: 'pending',
  current_step: 'gathering_inputs',
  error_message: undefined,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  agent_thoughts: [],
});

export const useTravelStore = create<TravelStore>()(
  immer((set) => ({
    ...createInitialState(),
    pendingFeedback: null,

    setSessionId: (id: string) =>
      set((state) => {
        state.session_id = id;
      }),

    setUserId: (id: string) =>
      set((state) => {
        state.user_id = id;
      }),

    setRoughDates: (dates: FuzzyDateRange) =>
      set((state) => {
        state.rough_dates = dates;
        state.updated_at = new Date().toISOString();
      }),

    setDestinations: (destinations: DestinationInput[]) =>
      set((state) => {
        state.destinations = destinations;
        state.updated_at = new Date().toISOString();
      }),

    addDestination: (destination: DestinationInput) =>
      set((state) => {
        // Check if destination already exists
        const exists = state.destinations.some((d) => d.name === destination.name);
        if (!exists) {
          state.destinations.push(destination);
          state.updated_at = new Date().toISOString();
        }
      }),

    removeDestination: (name: string) =>
      set((state) => {
        state.destinations = state.destinations.filter((d) => d.name !== name);
        state.updated_at = new Date().toISOString();
      }),

    setPreferences: (prefs: TravelPreferences) =>
      set((state) => {
        state.preferences = prefs;
        state.updated_at = new Date().toISOString();
      }),

    setConfirmedDates: (dates: ConfirmedDateRange) =>
      set((state) => {
        state.confirmed_dates = dates;
        state.updated_at = new Date().toISOString();
      }),

    setItinerary: (itinerary: Itinerary) =>
      set((state) => {
        state.itinerary = itinerary;
        state.updated_at = new Date().toISOString();
      }),

    setUIStatus: (status: TravelState['ui_status']) =>
      set((state) => {
        state.ui_status = status;
        state.updated_at = new Date().toISOString();
      }),

    setCurrentStep: (step: string) =>
      set((state) => {
        state.current_step = step;
        state.updated_at = new Date().toISOString();
      }),

    setErrorMessage: (error: string | null) =>
      set((state) => {
        state.error_message = error ?? undefined;
        state.updated_at = new Date().toISOString();
      }),

    addThought: (thought: string) =>
      set((state) => {
        state.agent_thoughts.push(thought);
        state.updated_at = new Date().toISOString();
      }),

    clearThoughts: () =>
      set((state) => {
        state.agent_thoughts = [];
      }),

    loadState: (newState: TravelState) =>
      set((state) => {
        return { ...state, ...newState };
      }),

    setPendingFeedback: (req: HumanFeedbackRequest | null) =>
      set((state) => {
        state.pendingFeedback = req;
      }),

    reset: () => set({ ...createInitialState(), pendingFeedback: null }),
  }))
);
