/**
 * useCrewEvents – Custom hook for consuming the /ws/events event stream.
 * Opens a WebSocket on mount, parses incoming CrewAI events, and provides
 * the accumulated event list plus a clearEvents helper.
 */

import { useEffect, useRef, useState, useCallback } from 'react';

export interface CrewEvent {
  type: string;
  agent?: string;
  output?: string;
  task?: string;
  tool?: string;
  error?: string;
  model?: string;
  crew?: string;
  flow?: string;
  method?: string;
  chunk?: string;
  timestamp: string;
}

interface UseCrewEventsResult {
  events: CrewEvent[];
  connected: boolean;
  clearEvents: () => void;
}

export function useCrewEvents(wsUrl: string): UseCrewEventsResult {
  const [events, setEvents] = useState<CrewEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const clearEvents = useCallback(() => setEvents([]), []);

  useEffect(() => {
    if (!wsUrl) return;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (msg) => {
      try {
        const event: CrewEvent = JSON.parse(msg.data);
        setEvents((prev) => [...prev, event]);
      } catch {
        // ignore non-JSON frames
      }
    };

    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    return () => {
      ws.close();
      setConnected(false);
    };
  }, [wsUrl]);

  return { events, connected, clearEvents };
}
