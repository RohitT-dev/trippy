/**
 * useWebSocket - Custom hook for WebSocket connection management
 * Handles connection, reconnection, message routing, and cleanup
 */

import { useEffect, useRef, useCallback, useLayoutEffect } from 'react';
import { WebSocketMessage } from '../store/types';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (message: WebSocketMessage) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
  onClose?: () => void;
  autoConnect?: boolean;
  reconnectAttempts?: number;
  reconnectDelay?: number;
}

export const useWebSocket = ({
  url,
  onMessage,
  onError,
  onOpen,
  onClose,
  autoConnect = true,
  reconnectAttempts = 5,
  reconnectDelay = 3000,
}: UseWebSocketOptions) => {
  const webSocketRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const isManuallyClosedRef = useRef(false);

  // Keep callback refs up-to-date without triggering reconnects.
  // Using useLayoutEffect ensures the refs are current before the next paint.
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  useLayoutEffect(() => { onMessageRef.current = onMessage; });
  useLayoutEffect(() => { onErrorRef.current = onError; });
  useLayoutEffect(() => { onOpenRef.current = onOpen; });
  useLayoutEffect(() => { onCloseRef.current = onClose; });

  const connect = useCallback(() => {
    if (webSocketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      webSocketRef.current = new WebSocket(url);

      webSocketRef.current.onopen = () => {
        console.log('WebSocket connected:', url);
        reconnectCountRef.current = 0;
        onOpenRef.current?.();
      };

      webSocketRef.current.onmessage = (event: MessageEvent) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          onMessageRef.current?.(message);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      webSocketRef.current.onerror = (event: Event) => {
        console.error('WebSocket error:', event);
        onErrorRef.current?.(event);
      };

      webSocketRef.current.onclose = () => {
        console.log('WebSocket disconnected');
        onCloseRef.current?.();

        // Attempt to reconnect if not manually closed
        if (!isManuallyClosedRef.current && reconnectCountRef.current < reconnectAttempts) {
          reconnectCountRef.current++;
          console.log(
            `Attempting to reconnect (${reconnectCountRef.current}/${reconnectAttempts})...`
          );
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelay);
        }
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      onErrorRef.current?.(err as Event);
    }
  // Only reconnect when the URL changes — callbacks are accessed via refs.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, reconnectAttempts, reconnectDelay]);

  const disconnect = useCallback(() => {
    isManuallyClosedRef.current = true;
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (webSocketRef.current) {
      webSocketRef.current.close();
      webSocketRef.current = null;
    }
  }, []);

  const send = useCallback((message: any) => {
    if (webSocketRef.current?.readyState === WebSocket.OPEN) {
      webSocketRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  const isConnected =
    webSocketRef.current?.readyState === WebSocket.OPEN;

  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return {
    isConnected,
    send,
    disconnect,
    connect,
  };
};
