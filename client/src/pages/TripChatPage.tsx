/**
 * TripChatPage — Natural language trip input + live planning flow.
 *
 * Stage 1 (input):  Large NL textarea + auto-parsed destination chips + send button.
 * Stage 2 (flow):   ProgressTimeline, ThoughtStream, HumanFeedbackCard, Stop/Retry.
 * Stage 3 (result): Itinerary summary + "Plan Another Trip".
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useTravelFlow, EVENTS_WS_URL } from '../hooks/useTravelFlow';
import { useWebSocket } from '../hooks/useWebSocket';
import { useTravelStore } from '../store/useTravelStore';
import { ProgressTimeline } from '../components/ProgressTimeline';
import { ThoughtStream } from '../components/ThoughtStream';
import { HumanFeedbackCard } from '../components/HumanFeedbackCard';
import { DestinationInput, FuzzyDateRange } from '../store/types';

// ---------------------------------------------------------------------------
// NL parser — extracts destinations, duration, season from free text
// ---------------------------------------------------------------------------

const STOP_WORDS = new Set([
  'I', 'My', 'Me', 'We', 'Our', 'They', 'You', 'Your', 'He', 'She', 'It',
  'The', 'A', 'An', 'In', 'On', 'At', 'To', 'For', 'Of', 'By', 'With',
  'From', 'Into', 'Through', 'During', 'After', 'Before', 'Near', 'Around',
  'And', 'Or', 'But', 'So', 'Also',
  'Want', 'Would', 'Like', 'Love', 'Plan', 'Travel', 'Visit', 'Explore',
  'Going', 'Looking', 'Take', 'Have', 'Been', 'This', 'That', 'These', 'Those',
  'Days', 'Weeks', 'Week', 'Month', 'Year', 'Day', 'Night', 'Nights', 'Weekend',
  'Spring', 'Summer', 'Autumn', 'Fall', 'Winter',
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
  'Perfect', 'Amazing', 'Great', 'Best', 'Dream', 'Wonderful', 'Beautiful',
  'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten',
]);

function parseTrip(text: string): { destinations: DestinationInput[]; roughDates: FuzzyDateRange } {
  const destSet = new Set<string>();

  // Match single or two-word capitalized phrases (e.g. "Japan", "South Korea")
  const regex = /\b([A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?)\b/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const word = match[1];
    const first = word.split(' ')[0];
    if (!STOP_WORDS.has(first) && !STOP_WORDS.has(word) && word.length > 2) {
      destSet.add(word);
    }
  }

  const destinations: DestinationInput[] = [...destSet].map((name, i) => ({
    name,
    type: 'city',
    priority: i + 1,
  }));

  // Duration
  let rough_duration: string | undefined;
  const dayMatch = text.match(/(\d+)\s*(?:day|night)s?/i);
  const weekNumMatch = text.match(/(\d+)\s*week(?:s)?/i);
  const weekWordMatch = text.match(/\ba\s+week\b/i);
  if (dayMatch) {
    rough_duration = `${dayMatch[1]} days`;
  } else if (weekNumMatch) {
    const n = parseInt(weekNumMatch[1]);
    rough_duration = `${n} week${n > 1 ? 's' : ''}`;
  } else if (weekWordMatch) {
    rough_duration = '1 week';
  }

  // Season / month
  const lower = text.toLowerCase();
  const seasons = ['spring', 'summer', 'autumn', 'fall', 'winter'];
  const months = [
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december',
  ];
  const rough_season =
    seasons.find((s) => lower.includes(s)) ||
    months.find((m) => lower.includes(m));

  return { destinations, roughDates: { rough_season, rough_duration } };
}

// ---------------------------------------------------------------------------
// Example prompts
// ---------------------------------------------------------------------------

const EXAMPLES = [
  {
    label: 'Weekend city break',
    prompt: 'A long weekend in Barcelona — food, architecture, and the beach. Probably spring.',
  },
  {
    label: 'Multi-country adventure',
    prompt: 'Two weeks exploring Japan and South Korea in summer — temples, street food, and nature.',
  },
  {
    label: 'Tropical escape',
    prompt: '10 days in Bali and Lombok in October — beaches, rice terraces, and relaxation.',
  },
  {
    label: 'Cultural immersion',
    prompt: '3 weeks in India visiting Rajasthan and Kerala in winter — culture, food, and history.',
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  onGoToPreferences: () => void;
}

export const TripChatPage = ({ onGoToPreferences }: Props) => {
  const flow = useTravelFlow();
  const store = useTravelStore();
  const [tripText, setTripText] = useState('');
  const [destinations, setDestinations] = useState<DestinationInput[]>([]);
  const [newDest, setNewDest] = useState('');
  const [parsedDates, setParsedDates] = useState<FuzzyDateRange>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-parse whenever text changes
  useEffect(() => {
    if (tripText.trim().length > 10) {
      const { destinations: parsed, roughDates } = parseTrip(tripText);
      setDestinations(parsed);
      setParsedDates(roughDates);
    } else {
      setDestinations([]);
      setParsedDates({});
    }
  }, [tripText]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${ta.scrollHeight}px`;
    }
  }, [tripText]);

  // WebSocket connection
  const { isConnected } = useWebSocket({
    url: EVENTS_WS_URL,
    onMessage: flow.handleWebSocketMessage,
    autoConnect: !!flow.sessionId,
  });

  // Show results once complete
  useEffect(() => {
    if (flow.status === 'complete' && flow.itinerary) {
      setShowResults(true);
    }
  }, [flow.status, flow.itinerary]);

  const addDestination = useCallback(() => {
    const name = newDest.trim();
    if (!name) return;
    if (!destinations.find((d) => d.name.toLowerCase() === name.toLowerCase())) {
      setDestinations((prev) => [
        ...prev,
        { name, type: 'city', priority: prev.length + 1 },
      ]);
    }
    setNewDest('');
  }, [newDest, destinations]);

  const removeDestination = (name: string) =>
    setDestinations((prev) => prev.filter((d) => d.name !== name));

  const handleSubmit = async () => {
    if (!tripText.trim() || destinations.length === 0) return;
    setIsSubmitting(true);
    try {
      await flow.initializePlan({
        rough_dates: parsedDates,
        destinations,
        preferences: store.preferences,
        trip_description: tripText.trim(),
        user_name: store.userProfile?.name || undefined,
        user_age: store.userProfile?.age || undefined,
      });
    } catch (err) {
      console.error('Failed to start planning:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setShowResults(false);
    setTripText('');
    setDestinations([]);
    setParsedDates({});
    store.reset();
  };

  const isActive = (
    ['researching', 'awaiting_date_confirmation', 'awaiting_itinerary_confirmation', 'awaiting_user'] as const
  ).includes(flow.status as any);

  const missingCountry = !store.preferences.origin_country;
  const canSubmit = !isSubmitting && tripText.trim().length > 0 && destinations.length > 0;

  // ── Results ──────────────────────────────────────────────────────────────
  if (showResults && flow.itinerary) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center py-16 px-4">
        <div className="w-full max-w-3xl space-y-4">
          <div className="bg-white rounded-card border border-slate-200 shadow-sm p-8">
            <span className="text-xs font-semibold text-primary uppercase tracking-widest">
              Your Itinerary
            </span>
            <h1 className="text-3xl font-extrabold text-slate-900 mt-2 mb-3 tracking-tight leading-tight">
              {flow.itinerary.trip_title}
            </h1>
            <p className="text-slate-600 leading-relaxed mb-6">{flow.itinerary.summary}</p>
            {flow.itinerary.estimated_budget && (
              <div className="inline-flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2">
                <span className="text-emerald-700 font-bold text-lg">
                  {flow.itinerary.estimated_budget}
                </span>
                <span className="text-emerald-600 text-sm font-medium">estimated total</span>
              </div>
            )}
          </div>
          <button
            onClick={handleReset}
            className="w-full py-3 rounded-card text-sm font-semibold text-white bg-primary hover:bg-primary-dark active:scale-95 transition-all shadow-sm"
          >
            ✦ Plan Another Trip
          </button>
        </div>
      </div>
    );
  }

  // ── Planning flow ─────────────────────────────────────────────────────────
  if (flow.sessionId) {
    return (
      <div className="min-h-screen bg-slate-50 py-10 px-4">
        <div className="max-w-3xl mx-auto space-y-4">
          {/* Connection pill */}
          <div
            className={`flex items-center gap-2.5 px-4 py-3 rounded-card text-sm font-medium border ${
              isConnected
                ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                : 'bg-amber-50 border-amber-200 text-amber-700'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full flex-shrink-0 ${
                isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-400'
              }`}
            />
            {isConnected ? 'Connected to planning agents' : 'Connecting…'}
          </div>

          {/* Stop button */}
          {isActive && (
            <div className="flex justify-end">
              <button
                onClick={() => flow.stopFlow(flow.sessionId!)}
                className="px-4 py-2 rounded-card text-sm font-semibold text-white bg-red-500 hover:bg-red-600 active:scale-95 transition-all"
              >
                ⛔ Stop Planning
              </button>
            </div>
          )}

          {/* Error / stopped */}
          {(flow.status === 'error' || (flow.status as string) === 'stopped') && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-card text-red-800">
              <p className="font-semibold">
                {(flow.status as string) === 'stopped'
                  ? '⛔ Planning was stopped.'
                  : `❌ ${flow.error ?? 'Something went wrong'}`}
              </p>
              <div className="flex gap-3 mt-3">
                <button
                  onClick={() => flow.retryFlow()}
                  className="px-4 py-2 bg-primary text-white text-sm rounded-card hover:bg-primary-dark transition-colors font-semibold"
                >
                  🔄 Retry
                </button>
                <button
                  onClick={handleReset}
                  className="px-4 py-2 bg-white border border-slate-200 text-slate-600 text-sm rounded-card hover:bg-slate-50 transition-colors font-medium"
                >
                  Start over
                </button>
              </div>
            </div>
          )}

          {/* Human feedback gate */}
          {flow.pendingFeedback && (
            <HumanFeedbackCard
              feedback={flow.pendingFeedback}
              onSubmit={(text, selectedDates) =>
                flow.submitFeedback(flow.sessionId!, text, selectedDates)
              }
            />
          )}

          <ProgressTimeline status={flow.status} currentStep={flow.currentStep} />
          <ThoughtStream thoughts={flow.thoughts} isLoading={flow.status === 'researching'} />
        </div>
      </div>
    );
  }

  // ── Input stage ───────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4 py-16">
      <div className="w-full max-w-2xl">
        {/* Hero */}
        <div className="text-center mb-10">
          <h1 className="text-5xl font-extrabold text-slate-900 tracking-tight leading-tight mb-4">
            Where are you<br />
            <span className="text-primary">headed next?</span>
          </h1>
          <p className="text-slate-500 text-lg">
            Describe your dream trip and our AI agents will plan everything.
          </p>
        </div>

        {/* Main input card */}
        <div className="bg-white rounded-card border border-slate-200 shadow-sm overflow-hidden">
          {/* Textarea */}
          <div className="relative p-4 pb-2">
            <span className="absolute top-5 left-5 text-primary text-lg select-none pointer-events-none">
              ✦
            </span>
            <textarea
              ref={textareaRef}
              value={tripText}
              onChange={(e) => setTripText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit();
              }}
              placeholder="e.g. I'd love a 2-week adventure through Japan and South Korea in summer, exploring temples, street food, and hiking trails…"
              rows={3}
              className="w-full pl-8 pr-2 py-1 resize-none text-slate-900 text-base placeholder-slate-400 focus:outline-none bg-transparent leading-relaxed min-h-[72px]"
            />
          </div>

          {/* Destination chips */}
          {destinations.length > 0 && (
            <div className="px-4 pb-3 flex flex-wrap gap-2">
              {destinations.map((dest) => (
                <span
                  key={dest.name}
                  className="inline-flex items-center gap-1.5 bg-blue-50 text-primary border border-blue-200 text-sm font-semibold px-3 py-1 rounded-full"
                >
                  📍 {dest.name}
                  <button
                    onClick={() => removeDestination(dest.name)}
                    className="text-blue-400 hover:text-blue-600 font-bold leading-none ml-0.5"
                    aria-label={`Remove ${dest.name}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Manual destination input */}
          <div className="px-4 pb-3 flex gap-2">
            <input
              type="text"
              value={newDest}
              onChange={(e) => setNewDest(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addDestination()}
              placeholder="Add a destination manually…"
              className="flex-1 text-sm bg-slate-50 border border-slate-200 rounded-card px-3 py-2 text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
            />
            <button
              onClick={addDestination}
              className="px-3 py-2 text-sm font-semibold text-primary bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-card transition-colors"
            >
              + Add
            </button>
          </div>

          {/* Divider */}
          <div className="border-t border-slate-100" />

          {/* Footer row */}
          <div className="flex items-center justify-between px-4 py-3">
            {parsedDates.rough_duration || parsedDates.rough_season ? (
              <span className="text-xs text-slate-500 font-medium">
                📅{' '}
                {[parsedDates.rough_duration, parsedDates.rough_season]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            ) : (
              <span className="text-xs text-slate-400 font-meta">⌘ Enter to send</span>
            )}
            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="flex items-center gap-2 px-5 py-2.5 rounded-card text-sm font-semibold text-white bg-primary hover:bg-primary-dark active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  Starting…
                </>
              ) : (
                <>✦ Start Planning</>
              )}
            </button>
          </div>
        </div>

        {/* Origin country nudge */}
        {missingCountry && (
          <div className="mt-4 flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-card text-amber-800">
            <span className="text-base mt-0.5">⚠️</span>
            <div className="flex-1">
              <p className="text-sm font-semibold">Set your country of origin</p>
              <p className="text-xs text-amber-600 mt-0.5">
                Needed for accurate visa checks and flight estimates.
              </p>
            </div>
            <button
              onClick={onGoToPreferences}
              className="text-sm font-semibold text-amber-700 hover:text-amber-900 underline underline-offset-2 whitespace-nowrap"
            >
              Set up →
            </button>
          </div>
        )}

        {/* Example prompts */}
        <div className="mt-8">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Need inspiration?
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {EXAMPLES.map(({ label, prompt }) => (
              <button
                key={label}
                onClick={() => setTripText(prompt)}
                className="text-left px-4 py-3.5 bg-white border border-slate-200 rounded-card hover:border-primary/40 hover:shadow-sm active:scale-[0.99] transition-all group"
              >
                <p className="text-xs font-semibold text-primary mb-1">{label}</p>
                <p className="text-xs text-slate-500 group-hover:text-slate-700 leading-relaxed line-clamp-2">
                  {prompt}
                </p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
