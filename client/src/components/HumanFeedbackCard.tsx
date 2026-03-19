/**
 * HumanFeedbackCard — rendered whenever the backend flow pauses at a
 * @human_feedback step.  It shows the agent's proposal and lets the user
 * approve, reject, or type custom free-form feedback.
 *
 * For date_confirmation with rough dates: shows selectable date-option cards.
 */

import { useState } from 'react';
import { HumanFeedbackRequest, DateOption } from '../store/types';

interface Props {
  feedback: HumanFeedbackRequest;
  onSubmit: (text: string, selectedDates?: DateOption) => Promise<void>;
}

const STEP_CONFIG: Record<
  HumanFeedbackRequest['step'],
  {
    icon: string;
    approveLabel: string;
    approveText: string;
    rejectLabel: string;
    rejectText: string;
  }
> = {
  date_confirmation: {
    icon: '📅',
    approveLabel: 'Confirm Dates',
    approveText: 'approve, the dates look good',
    rejectLabel: 'Request Different Dates',
    rejectText: 'please suggest different dates',
  },
  itinerary_review: {
    icon: '🗺️',
    approveLabel: 'Approve Itinerary',
    approveText: 'approve, the itinerary looks great',
    rejectLabel: 'Request Changes',
    rejectText: 'please revise the itinerary',
  },
};

/** Format an ISO date string to a readable "Mon D, YYYY" label. */
function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

/** Format a month range label, e.g. "Jun 2 – Jun 16, 2026" */
function fmtRange(start: string, end: string) {
  const s = new Date(start);
  const e = new Date(end);
  const sLabel = s.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const eLabel = e.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  return `${sLabel} – ${eLabel}`;
}

export const HumanFeedbackCard = ({ feedback, onSubmit }: Props) => {
  const [customText, setCustomText] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  const config = STEP_CONFIG[feedback.step] ?? {
    icon: '💬',
    approveLabel: 'Approve',
    approveText: 'approve',
    rejectLabel: 'Reject',
    rejectText: 'reject',
  };

  const handleSubmit = async (text: string, dates?: DateOption) => {
    setLoading(true);
    try {
      await onSubmit(text, dates);
    } finally {
      setLoading(false);
    }
  };

  // ── Date option cards (shown when agent returned multiple rough-date windows) ─
  const renderDateOptions = () => {
    const data = feedback.data as any;
    const options: DateOption[] = data.proposed_options ?? [];
    if (!options.length) return null;

    return (
      <div className="space-y-2">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Choose a travel window
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {options.map((opt, idx) => {
            const isSelected = selectedIdx === idx;
            return (
              <button
                key={idx}
                onClick={() => setSelectedIdx(isSelected ? null : idx)}
                disabled={loading}
                className={`text-left rounded-lg border-2 p-3 transition-all disabled:opacity-50 ${
                  isSelected
                    ? 'border-blue-500 bg-blue-50 shadow-md'
                    : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/40'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-gray-400">Option {idx + 1}</span>
                  {isSelected && (
                    <span className="text-xs font-bold text-blue-600">✓ Selected</span>
                  )}
                </div>
                <p className="font-semibold text-gray-900 text-sm leading-snug">
                  {fmtRange(opt.start, opt.end)}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">{opt.duration_days} days</p>
                {opt.rationale && (
                  <p className="text-xs text-gray-600 mt-1 leading-relaxed italic">
                    {opt.rationale}
                  </p>
                )}
              </button>
            );
          })}
        </div>

        {/* Confirm selected option */}
        {selectedIdx !== null && (
          <button
            onClick={() => handleSubmit(
              `approve option ${selectedIdx + 1}: ${options[selectedIdx].start} to ${options[selectedIdx].end}`,
              options[selectedIdx],
            )}
            disabled={loading}
            className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50
                       text-white font-semibold rounded-lg transition-colors mt-1"
          >
            ✓ Confirm: {fmtRange(options[selectedIdx].start, options[selectedIdx].end)}
          </button>
        )}
      </div>
    );
  };

  // ── Single-date panel (exact dates; no options array) ─────────────────────
  const renderSingleDatePanel = () => {
    const { proposed_start, proposed_end, duration_days, date_analysis_summary } = feedback.data as any;
    if (!proposed_start) return null;
    return (
      <div className="bg-blue-50 rounded-lg p-4 space-y-2 text-sm">
        <div className="flex flex-wrap gap-6">
          <div>
            <span className="font-semibold text-gray-600">Start: </span>
            <span className="text-blue-800">{fmtDate(proposed_start)}</span>
          </div>
          <div>
            <span className="font-semibold text-gray-600">End: </span>
            <span className="text-blue-800">{fmtDate(proposed_end)}</span>
          </div>
          {duration_days && (
            <div>
              <span className="font-semibold text-gray-600">Duration: </span>
              <span className="text-blue-800">{duration_days} days</span>
            </div>
          )}
        </div>
        {date_analysis_summary && (
          <p className="text-gray-600 text-xs leading-relaxed">{date_analysis_summary}</p>
        )}
      </div>
    );
  };

  // ── Itinerary review panel ────────────────────────────────────────────────
  const renderItineraryPanel = () => {
    const { trip_title, summary, days, estimated_budget } = feedback.data as any;
    return (
      <div className="bg-purple-50 rounded-lg p-4 space-y-2 text-sm">
        {trip_title && <p className="font-semibold text-purple-900">{trip_title}</p>}
        <div className="flex gap-6 text-gray-600">
          {days > 0 && <span>📆 {days} days</span>}
          {estimated_budget && <span>💰 {estimated_budget}</span>}
        </div>
        {summary && <p className="text-gray-600 text-xs leading-relaxed">{summary}</p>}
      </div>
    );
  };

  const hasOptions = feedback.step === 'date_confirmation' &&
    ((feedback.data as any).proposed_options ?? []).length > 0;

  return (
    <div className="bg-white rounded-xl shadow-lg border-2 border-amber-300 p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <span className="text-3xl">{config.icon}</span>
        <div>
          <h3 className="font-bold text-gray-900 text-lg">Your Input Needed</h3>
          <p className="text-gray-600 text-sm">{feedback.message}</p>
        </div>
      </div>

      {/* Step-specific content */}
      {feedback.step === 'date_confirmation' && (
        hasOptions ? renderDateOptions() : renderSingleDatePanel()
      )}
      {feedback.step === 'itinerary_review' && renderItineraryPanel()}

      {/* Quick-action buttons (always shown for non-option flows; hidden when options exist) */}
      {!hasOptions && (
        <div className="flex gap-3">
          <button
            onClick={() => handleSubmit(config.approveText)}
            disabled={loading}
            className="flex-1 py-2.5 px-4 bg-green-600 hover:bg-green-700 disabled:opacity-50
                       text-white font-semibold rounded-lg transition-colors"
          >
            ✓ {config.approveLabel}
          </button>
          <button
            onClick={() => handleSubmit(config.rejectText)}
            disabled={loading}
            className="flex-1 py-2.5 px-4 bg-gray-200 hover:bg-gray-300 disabled:opacity-50
                       text-gray-800 font-semibold rounded-lg transition-colors"
          >
            ✗ {config.rejectLabel}
          </button>
        </div>
      )}

      {/* Custom text input */}
      <div className="space-y-2">
        <label className="text-xs text-gray-500 font-medium">
          {hasOptions
            ? 'Or describe what you\'re looking for instead:'
            : 'Or type custom feedback (the AI will interpret it):'}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && customText.trim() && handleSubmit(customText.trim())}
            placeholder={hasOptions
              ? "e.g. 'none of these work, try late August' "
              : "e.g. 'looks good but can we push start to August?'"}
            disabled={loading}
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm
                       focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:opacity-50"
          />
          <button
            onClick={() => customText.trim() && handleSubmit(customText.trim())}
            disabled={loading || !customText.trim()}
            className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-40
                       text-white font-semibold rounded-lg transition-colors text-sm"
          >
            Send
          </button>
        </div>
      </div>

      {loading && (
        <p className="text-center text-sm text-gray-500 animate-pulse">
          ⏳ Processing your response…
        </p>
      )}
    </div>
  );
};

