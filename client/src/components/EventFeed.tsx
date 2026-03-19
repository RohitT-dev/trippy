/**
 * EventFeed – real-time CrewAI event stream viewer.
 *
 * Connects to ws://localhost:8000/ws/events, displays a live scrollable
 * feed of agent/task/LLM/tool/flow events, and provides a "Kick Off"
 * button that starts a new flow run via POST /api/events/kickoff.
 */

import { useEffect, useRef, useState } from 'react';
import { useCrewEvents, CrewEvent } from '../hooks/useCrewEvents';

const WS_URL = 'ws://localhost:8000/ws/events';
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Colour + label helpers
// ---------------------------------------------------------------------------

function badgeClass(type: string): string {
  if (type.startsWith('crew_')) return 'bg-purple-100 text-purple-800';
  if (type.startsWith('agent_')) return 'bg-blue-100 text-blue-800';
  if (type.startsWith('task_')) return 'bg-green-100 text-green-800';
  if (type.startsWith('llm_')) return 'bg-yellow-100 text-yellow-800';
  if (type.startsWith('tool_')) return 'bg-orange-100 text-orange-800';
  if (type.startsWith('flow_') || type.startsWith('method_')) return 'bg-indigo-100 text-indigo-800';
  if (type.includes('failed') || type.includes('error')) return 'bg-red-100 text-red-800';
  return 'bg-gray-100 text-gray-700';
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toTimeString().slice(0, 8);
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConnectionDot({ connected }: { connected: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-sm font-medium">
      <span
        className={`inline-block w-2.5 h-2.5 rounded-full ${
          connected ? 'bg-green-500 animate-pulse' : 'bg-red-400'
        }`}
      />
      {connected ? 'Connected' : 'Disconnected'}
    </span>
  );
}

function EventRow({ event, thinking }: { event: CrewEvent; thinking: boolean }) {
  const body = event.output ?? event.error ?? event.chunk ?? null;
  return (
    <div className="flex flex-col gap-0.5 py-2 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${badgeClass(event.type)}`}>
          {event.type}
        </span>
        {event.agent && (
          <span className="text-xs text-gray-600 font-medium">{event.agent}</span>
        )}
        {event.task && (
          <span className="text-xs text-gray-500 italic truncate max-w-xs">{event.task}</span>
        )}
        {event.tool && (
          <span className="text-xs text-gray-500">🔧 {event.tool}</span>
        )}
        {event.method && (
          <span className="text-xs text-gray-500">⚙️ {event.method}</span>
        )}
        <span className="ml-auto text-xs text-gray-400 tabular-nums shrink-0">
          {formatTime(event.timestamp)}
        </span>
      </div>
      {body && (
        <p className="text-xs text-gray-600 pl-1 mt-0.5 line-clamp-3 whitespace-pre-wrap break-words">
          {body}
        </p>
      )}
      {thinking && event.type === 'llm_call_started' && (
        <span className="text-xs text-yellow-600 animate-pulse pl-1">Thinking…</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface EventFeedProps {
  /** Extra CSS classes applied to the outermost container. */
  className?: string;
}

export function EventFeed({ className = '' }: EventFeedProps) {
  const { events, connected, clearEvents } = useCrewEvents(WS_URL);
  const [kicking, setKicking] = useState(false);
  const [kickError, setKickError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever new events arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  // Derive "thinking" state: an LLM call has started but not yet completed
  const lastLlmIdx = [...events].reverse().findIndex(
    (e) => e.type === 'llm_call_started' || e.type === 'llm_call_completed' || e.type === 'llm_call_failed',
  );
  const thinking =
    lastLlmIdx !== -1 &&
    events[events.length - 1 - lastLlmIdx]?.type === 'llm_call_started';

  const handleKickoff = async () => {
    setKicking(true);
    setKickError(null);
    clearEvents();
    try {
      const res = await fetch(`${API_BASE}/api/events/kickoff`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rough_dates: {},
          destinations: [{ name: 'Tokyo', type: 'city', priority: 1 }],
          preferences: {
            budget_level: 'moderate',
            travel_pace: 'moderate',
            travel_group_type: 'solo',
          },
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        setKickError(`Server error ${res.status}: ${text}`);
      }
    } catch (err) {
      setKickError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setKicking(false);
    }
  };

  return (
    <div className={`flex flex-col bg-white rounded-xl shadow-md border border-gray-200 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-gray-800">🧠 Agent Event Stream</h2>
          <ConnectionDot connected={connected} />
          {thinking && (
            <span className="text-xs text-yellow-600 font-medium animate-pulse">Thinking…</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {events.length > 0 && (
            <button
              onClick={clearEvents}
              className="text-xs text-gray-500 hover:text-gray-700 underline"
            >
              Clear
            </button>
          )}
          <button
            onClick={handleKickoff}
            disabled={kicking || !connected}
            className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {kicking ? 'Starting…' : 'Kick Off Crew'}
          </button>
        </div>
      </div>

      {/* Error banner */}
      {kickError && (
        <div className="px-4 py-2 bg-red-50 border-b border-red-200 text-xs text-red-700">
          {kickError}
        </div>
      )}

      {/* Event list */}
      <div className="flex-1 overflow-y-auto px-4 py-1 min-h-0 max-h-[480px]">
        {events.length === 0 ? (
          <p className="text-center text-gray-400 text-sm py-10">
            {connected
              ? 'Waiting for events… click "Kick Off Crew" to start.'
              : 'Connecting to event stream…'}
          </p>
        ) : (
          events.map((evt, idx) => (
            <EventRow
              key={idx}
              event={evt}
              thinking={thinking && idx === events.length - 1}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Footer counter */}
      {events.length > 0 && (
        <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 text-xs text-gray-400 text-right">
          {events.length} event{events.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}
