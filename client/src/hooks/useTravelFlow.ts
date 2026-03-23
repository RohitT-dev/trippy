/**
 * useTravelFlow - Custom hook for coordinating travel planning flow
 * Handles API communication and state synchronization
 */

import { useCallback, useRef, useLayoutEffect } from 'react';
import { useTravelStore } from '../store/useTravelStore';
import {
  PlanInitializeRequest,
  WebSocketMessage,
  TravelState,
  FuzzyDateRange,
  DestinationInput,
  TravelPreferences,
  ConfirmedDateRange,
  HumanFeedbackRequest,
  DateOption,
} from '../store/types';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
// Events WebSocket streams all CrewAI events including human_feedback_requested
export const EVENTS_WS_URL = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000') + '/ws/events';

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const useTravelFlow = () => {
  const store = useTravelStore();

  // Keep a ref to the latest store so the WebSocket message handler never
  // goes stale and never needs to be in a useCallback dependency array.
  const storeRef = useRef(store);
  useLayoutEffect(() => { storeRef.current = store; });

  /** Start the planning flow asynchronously; returns the new session_id immediately. */
  const initializePlan = useCallback(async (data: {
    rough_dates: FuzzyDateRange;
    destinations: DestinationInput[];
    preferences: TravelPreferences;
    confirmed_dates?: ConfirmedDateRange;
    trip_description?: string;
    user_name?: string;
    user_age?: string;
  }) => {
    store.setLastPlanRequest(data);
    try {
      const request: PlanInitializeRequest = {
        rough_dates: data.rough_dates,
        destinations: data.destinations,
        preferences: data.preferences,
        confirmed_dates: data.confirmed_dates,
        trip_description: data.trip_description,
        user_name: data.user_name,
        user_age: data.user_age,
        user_id: store.user_id,
      };

      // Use the async kickoff endpoint so the flow runs in the background
      // and streams events through /ws/events
      const response = await apiClient.post('/api/events/kickoff', request);
      const { session_id } = response.data;

      store.setSessionId(session_id);
      store.setUIStatus('researching');
      store.setCurrentStep('gathering_inputs');

      return session_id as string;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to initialize plan';
      store.setErrorMessage(message);
      throw error;
    }
  }, [store]);

  /** Submit free-form feedback (or a selected date option) for the currently paused step. */
  const submitFeedback = useCallback(async (
    sessionId: string,
    feedbackText: string,
    selectedDates?: DateOption,
  ) => {
    try {
      const body: Record<string, unknown> = { feedback_text: feedbackText };
      if (selectedDates) {
        body.selected_dates = {
          start_date: selectedDates.start,
          end_date: selectedDates.end,
          duration_days: selectedDates.duration_days,
        };
      }
      await apiClient.post(`/api/plan/${sessionId}/feedback`, body);
      // Clear the pending overlay immediately so the UI shifts to "processing"
      store.setPendingFeedback(null);
      store.setUIStatus('researching');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to submit feedback';
      store.setErrorMessage(message);
      throw error;
    }
  }, [store]);

  /** Stop the active flow for the current session. */
  const stopFlow = useCallback(async (sessionId: string) => {
    try {
      store.setUIStatus('stopping');
      await apiClient.post(`/api/plan/${sessionId}/stop`);
    } catch (error) {
      // If the server says 404 the flow already finished — treat as stopped
      store.setUIStatus('stopped');
    }
  }, [store]);

  /** Retry: reset local state and re-submit the last plan request. */
  const retryFlow = useCallback(async () => {
    const lastRequest = storeRef.current.lastPlanRequest;
    if (!lastRequest) return;
    store.reset();
    await initializePlan(lastRequest);
  }, [store, initializePlan]);

  const confirmDates = useCallback(async (sessionId: string) => {
    try {
      if (!store.confirmed_dates) {
        throw new Error('No confirmed dates set');
      }

      await apiClient.post(`/api/plan/${sessionId}/confirm`, {
        session_id: sessionId,
        confirmed_dates: store.confirmed_dates,
      });

      store.setUIStatus('researching');
      store.setCurrentStep('running_agents');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to confirm dates';
      store.setErrorMessage(message);
      throw error;
    }
  }, [store]);

  const fetchPlan = useCallback(async (sessionId: string) => {
    try {
      const response = await apiClient.get(`/api/plan/${sessionId}`);
      const { state } = response.data;
      return state;
    } catch (error) {
      console.error('Failed to fetch plan:', error);
      throw error;
    }
  }, []);

  const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
    const s = storeRef.current;
    // Filter by session_id when present so concurrent sessions don't cross-contaminate
    const msgSessionId = (message.data as any)?.session_id as string | undefined;
    if (msgSessionId && s.session_id && msgSessionId !== s.session_id) return;

    // Many CrewAI event broadcasts don't include a `data` field — guard against that.
    const data = message.data ?? {};

    switch (message.type) {
      // ── Frontend-native message types ──────────────────────────────────
      case 'thought':
        if (data.thought) s.addThought(data.thought);
        break;

      case 'status_update':
        if (data.status) s.setUIStatus(data.status as TravelState['ui_status']);
        if (data.current_step) s.setCurrentStep(data.current_step);
        break;

      case 'flow_state_update':
        if (data.ui_status) s.setUIStatus(data.ui_status as TravelState['ui_status']);
        if (data.current_step) s.setCurrentStep(data.current_step);
        break;

      case 'itinerary_ready':
        if (data.itinerary) {
          s.setItinerary(data.itinerary);
        }
        break;

      case 'human_feedback_requested': {
        const req: HumanFeedbackRequest = {
          step: data.step as HumanFeedbackRequest['step'],
          message: data.message,
          options: data.options,
          data: data,
          session_id: data.session_id ?? s.session_id,
        };
        s.setPendingFeedback(req);
        break;
      }

      case 'error':
      case 'flow_error':
        if (data.error) {
          s.setErrorMessage(data.error);
          s.setUIStatus('error');
        }
        break;

      case 'state_sync':
        if (message.data) s.loadState(message.data as TravelState);
        break;

      // ── CrewAI event types → map to agent thoughts ─────────────────────
      case 'crew_kickoff_started':
        s.addThought(`🚀 Planning crew started`);
        s.setUIStatus('researching');
        break;

      case 'crew_kickoff_completed':
        s.addThought(`✅ Planning crew finished`);
        break;

      case 'agent_execution_started': {
        const agent = data.agent ?? 'Agent';
        s.addThought(`🤖 ${agent}: starting…`);
        break;
      }

      case 'agent_execution_completed': {
        const agent = data.agent ?? 'Agent';
        s.addThought(`✅ ${agent}: done`);
        break;
      }

      case 'task_started': {
        const task = data.task ?? 'task';
        s.addThought(`📋 Task started: ${task}`);
        break;
      }

      case 'task_completed': {
        const task = data.task ?? 'task';
        s.addThought(`✅ Task completed: ${task}`);
        break;
      }

      case 'tool_usage_started': {
        const tool = data.tool ?? 'tool';
        s.addThought(`🔧 Using tool: ${tool}`);
        break;
      }

      case 'tool_usage_finished': {
        const tool = data.tool ?? 'tool';
        s.addThought(`🔧 Tool done: ${tool}`);
        break;
      }

      case 'method_execution_started': {
        const method = data.method ?? '';
        if (method) s.addThought(`⚙️ Flow step: ${method}`);
        break;
      }

      case 'flow_stopped':
        s.setUIStatus('stopped');
        s.setCurrentStep('stopped');
        s.setPendingFeedback(null);
        break;

      case 'flow_finished':
        s.setUIStatus('complete');
        s.setCurrentStep('finalized');
        break;

      default:
        // Silently ignore unknown events
        break;
    }
  // storeRef.current is always up-to-date via useLayoutEffect — no deps needed.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    // Current state
    sessionId: store.session_id,
    status: store.ui_status,
    currentStep: store.current_step,
    thoughts: store.agent_thoughts,
    itinerary: store.itinerary,
    error: store.error_message,
    pendingFeedback: store.pendingFeedback,

    // Store actions
    setRoughDates: store.setRoughDates,
    setDestinations: store.setDestinations,
    addDestination: store.addDestination,
    removeDestination: store.removeDestination,
    setPreferences: store.setPreferences,
    setConfirmedDates: store.setConfirmedDates,

    // Flow actions
    initializePlan,
    confirmDates,
    submitFeedback,
    stopFlow,
    retryFlow,
    handleWebSocketMessage,
    fetchPlan,
  };
};

// Export types for convenience
// Export types for convenience
export type { PlanInitializeRequest, TravelState } from '../store/types';

