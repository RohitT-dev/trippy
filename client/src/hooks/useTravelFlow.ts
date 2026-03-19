/**
 * useTravelFlow - Custom hook for coordinating travel planning flow
 * Handles API communication and state synchronization
 */

import { useCallback } from 'react';
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

  /** Start the planning flow asynchronously; returns the new session_id immediately. */
  const initializePlan = useCallback(async (data: {
    rough_dates: FuzzyDateRange;
    destinations: DestinationInput[];
    preferences: TravelPreferences;
    confirmed_dates?: ConfirmedDateRange;
  }) => {
    try {
      const request: PlanInitializeRequest = {
        rough_dates: data.rough_dates,
        destinations: data.destinations,
        preferences: data.preferences,
        confirmed_dates: data.confirmed_dates,
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
    // Filter by session_id when present so concurrent sessions don't cross-contaminate
    const msgSessionId = (message.data as any)?.session_id as string | undefined;
    if (msgSessionId && store.session_id && msgSessionId !== store.session_id) return;

    switch (message.type) {
      // ── Frontend-native message types ──────────────────────────────────
      case 'thought':
        if (message.data.thought) store.addThought(message.data.thought);
        break;

      case 'status_update':
        if (message.data.status) store.setUIStatus(message.data.status as TravelState['ui_status']);
        if (message.data.current_step) store.setCurrentStep(message.data.current_step);
        break;

      case 'flow_state_update':
        if (message.data.ui_status) store.setUIStatus(message.data.ui_status as TravelState['ui_status']);
        if (message.data.current_step) store.setCurrentStep(message.data.current_step);
        break;

      case 'itinerary_ready':
        if (message.data.itinerary) {
          store.setItinerary(message.data.itinerary);
        }
        break;

      case 'human_feedback_requested': {
        const req: HumanFeedbackRequest = {
          step: message.data.step as HumanFeedbackRequest['step'],
          message: message.data.message,
          options: message.data.options,
          data: message.data,
          session_id: message.data.session_id ?? store.session_id,
        };
        store.setPendingFeedback(req);
        break;
      }

      case 'error':
        if (message.data.error) {
          store.setErrorMessage(message.data.error);
          store.setUIStatus('error');
        }
        break;

      case 'state_sync':
        if (message.data) store.loadState(message.data as TravelState);
        break;

      // ── CrewAI event types → map to agent thoughts ─────────────────────
      case 'crew_kickoff_started':
        store.addThought(`🚀 Planning crew started`);
        store.setUIStatus('researching');
        break;

      case 'crew_kickoff_completed':
        store.addThought(`✅ Planning crew finished`);
        break;

      case 'agent_execution_started': {
        const agent = message.data.agent ?? 'Agent';
        store.addThought(`🤖 ${agent}: starting…`);
        break;
      }

      case 'agent_execution_completed': {
        const agent = message.data.agent ?? 'Agent';
        store.addThought(`✅ ${agent}: done`);
        break;
      }

      case 'task_started': {
        const task = message.data.task ?? 'task';
        store.addThought(`📋 Task started: ${task}`);
        break;
      }

      case 'task_completed': {
        const task = message.data.task ?? 'task';
        store.addThought(`✅ Task completed: ${task}`);
        break;
      }

      case 'tool_usage_started': {
        const tool = message.data.tool ?? 'tool';
        store.addThought(`🔧 Using tool: ${tool}`);
        break;
      }

      case 'tool_usage_finished': {
        const tool = message.data.tool ?? 'tool';
        store.addThought(`🔧 Tool done: ${tool}`);
        break;
      }

      case 'method_execution_started': {
        const method = message.data.method ?? '';
        if (method) store.addThought(`⚙️ Flow step: ${method}`);
        break;
      }

      case 'flow_finished':
        store.setUIStatus('complete');
        store.setCurrentStep('finalized');
        break;

      default:
        // Silently ignore unknown events
        break;
    }
  }, [store]);

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
    handleWebSocketMessage,
    fetchPlan,
  };
};

// Export types for convenience
// Export types for convenience
export type { PlanInitializeRequest, TravelState } from '../store/types';

