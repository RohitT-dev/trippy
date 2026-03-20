/**
 * PlannerPage - Main page for travel planning
 */

import { useEffect, useState } from 'react';
import { useTravelFlow, EVENTS_WS_URL } from '../hooks/useTravelFlow';
import { useWebSocket } from '../hooks/useWebSocket';
import { TravelForm } from '../components/TravelForm';
import { ProgressTimeline } from '../components/ProgressTimeline';
import { ThoughtStream } from '../components/ThoughtStream';
import { HumanFeedbackCard } from '../components/HumanFeedbackCard';
import { FuzzyDateRange, DestinationInput, TravelPreferences, ConfirmedDateRange } from '../store/types';

export const PlannerPage = () => {
  const flow = useTravelFlow();
  const [isInitializing, setIsInitializing] = useState(false);
  const [showResults, setShowResults] = useState(false);

  // Always connect to the shared /ws/events stream once a session is started
  const { isConnected } = useWebSocket({
    url: EVENTS_WS_URL,
    onMessage: flow.handleWebSocketMessage,
    autoConnect: !!flow.sessionId,
  });

  const handleFormSubmit = async (data: {
    roughDates: FuzzyDateRange;
    destinations: DestinationInput[];
    preferences: TravelPreferences;
    confirmedDates?: ConfirmedDateRange;
  }) => {
    try {
      setIsInitializing(true);
      await flow.initializePlan({
        rough_dates: data.roughDates,
        destinations: data.destinations,
        preferences: data.preferences,
        confirmed_dates: data.confirmedDates,
      });
    } catch (error) {
      console.error('Error initializing plan:', error);
    } finally {
      setIsInitializing(false);
    }
  };

  // Show results when planning is complete
  useEffect(() => {
    if (flow.status === 'complete' && flow.itinerary) {
      setShowResults(true);
    }
  }, [flow.status, flow.itinerary]);

  if (showResults && flow.itinerary) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-purple-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-lg shadow-lg p-8 mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-2">{flow.itinerary.trip_title}</h1>
            <p className="text-gray-600 text-lg mb-6">{flow.itinerary.summary}</p>

            {flow.itinerary.estimated_budget && (
              <p className="text-2xl font-semibold text-green-600 mb-4">
                Budget: {flow.itinerary.estimated_budget}
              </p>
            )}
          </div>

          <button
            onClick={() => {
              setShowResults(false);
              window.location.reload();
            }}
            className="mb-6 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Plan Another Trip
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-purple-50 py-12 px-4">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">✈️ AI Travel Planner</h1>
          <p className="text-gray-600 text-lg">Let AI agents plan your perfect trip</p>
        </div>

        {/* Main Content */}
        {!flow.sessionId ? (
          <TravelForm onSubmit={handleFormSubmit} isLoading={isInitializing} />
        ) : (
          <>
            {/* Status Indicator */}
            {isConnected && (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-green-800">
                ✓ Connected to planning agents
              </div>
            )}

            {/* Stop button — visible while the flow is actively running */}
            {flow.sessionId && (['researching', 'awaiting_date_confirmation', 'awaiting_itinerary_confirmation', 'awaiting_user'] as const).includes(flow.status as any) && (
              <div className="flex justify-end">
                <button
                  onClick={() => flow.stopFlow(flow.sessionId!)}
                  disabled={flow.status === 'stopping' as any}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  ⛔ Stop Planning
                </button>
              </div>
            )}

            {/* Error / stopped banner with Retry option */}
            {(flow.status === 'error' || flow.status === 'stopped' as any) && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
                <p className="font-medium">
                  {flow.status === 'stopped'
                    ? '⛔ Planning was stopped.'
                    : `❌ Error: ${flow.error ?? 'Something went wrong'}`}
                </p>
                <p className="text-sm mt-1 text-red-600">You can retry with the same inputs or go back and change them.</p>
                <div className="flex gap-3 mt-3">
                  <button
                    onClick={() => flow.retryFlow()}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                  >
                    🔄 Retry
                  </button>
                </div>
              </div>
            )}

            {/* Human Feedback Gate — renders when the flow is paused waiting for input */}
            {flow.pendingFeedback && (
              <HumanFeedbackCard
                feedback={flow.pendingFeedback}
                onSubmit={(text, selectedDates) => flow.submitFeedback(flow.sessionId!, text, selectedDates)}
              />
            )}

            {/* Progress Timeline */}
            <ProgressTimeline status={flow.status} currentStep={flow.currentStep} />

            {/* Agent Thoughts */}
            <ThoughtStream
              thoughts={flow.thoughts}
              isLoading={flow.status === 'researching'}
            />

            {/* Session Info */}
            <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
              <p className="text-sm text-gray-600">
                <span className="font-semibold">Session ID:</span> {flow.sessionId}
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
