/**
 * ProgressTimeline - Visual timeline showing agent progress
 */

import { TravelState } from '../store/types';

interface ProgressTimelineProps {
  status: TravelState['ui_status'];
  currentStep: string;
}

const STEPS = [
  { id: 'gathering_inputs',            label: 'Gathering Inputs',         icon: '📝' },
  { id: 'interpreting_trip',           label: 'Interpreting Your Trip',   icon: '🗺️' },
  { id: 'analyzing_dates',             label: 'Analysing Dates',          icon: '📅' },
  { id: 'researching_destinations',    label: 'Researching Destinations', icon: '🌍' },
  { id: 'planning_logistics',          label: 'Planning Logistics',       icon: '✈️' },
  { id: 'awaiting_confirmation',       label: 'Ready for Review',         icon: '👀' },
  { id: 'running_agents',              label: 'Creating Itinerary',       icon: '🤖' },
  { id: 'itinerary_ready',             label: 'Done!',                    icon: '🎉' },
];

export const ProgressTimeline = ({ status, currentStep }: ProgressTimelineProps) => {
  const currentStepIndex = STEPS.findIndex((s) => s.id === currentStep);

  return (
    <div className="w-full max-w-4xl mx-auto p-6 bg-white rounded-lg shadow">
      <h3 className="text-lg font-semibold text-gray-900 mb-6">Planning Progress</h3>

      <div className="space-y-4">
        {STEPS.map((step, index) => {
          const isCompleted = index < currentStepIndex;
          const isCurrent = index === currentStepIndex;

          return (
            <div key={step.id} className="flex items-center gap-4">
              {/* Step Circle */}
              <div
                className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center font-bold text-xl ${
                  isCompleted
                    ? 'bg-green-100 text-green-700'
                    : isCurrent
                    ? 'bg-blue-100 text-blue-700 ring-2 ring-blue-500 ring-offset-2'
                    : 'bg-gray-200 text-gray-600'
                }`}
              >
                {step.icon}
              </div>

              {/* Step Info */}
              <div className="flex-1">
                <p
                  className={`font-medium ${
                    isCompleted
                      ? 'text-green-700'
                      : isCurrent
                      ? 'text-blue-700'
                      : 'text-gray-500'
                  }`}
                >
                  {step.label}
                </p>
                {isCurrent && status === 'researching' && (
                  <p className="text-sm text-gray-600 mt-1">Research in progress...</p>
                )}
              </div>

              {/* Check mark for completed */}
              {isCompleted && <span className="text-green-600 text-2xl">✓</span>}
            </div>
          );
        })}
      </div>

      {/* Status Bar */}
      <div className="mt-8 p-4 bg-blue-50 rounded-md">
        <p className="text-sm text-gray-700">
          <span className="font-semibold">Current Status:</span> {status}
        </p>
      </div>
    </div>
  );
};
