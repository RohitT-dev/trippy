/**
 * ThoughtStream - Displays real-time agent thoughts
 */

import { useEffect, useRef } from 'react';

interface ThoughtStreamProps {
  thoughts: string[];
  isLoading?: boolean;
}

export const ThoughtStream = ({ thoughts, isLoading = false }: ThoughtStreamProps) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new thoughts arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [thoughts]);

  return (
    <div className="w-full max-w-4xl mx-auto p-6 bg-white rounded-lg shadow">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Agent Thoughts</h3>

      <div
        ref={containerRef}
        className="bg-gray-50 border border-gray-200 rounded-md p-4 h-64 overflow-y-auto font-mono text-sm space-y-2"
      >
        {thoughts.length === 0 ? (
          <p className="text-gray-500">Waiting for agents to start thinking...</p>
        ) : (
          thoughts.map((thought, idx) => (
            <div key={idx} className="text-gray-800 pb-2 border-b border-gray-200 last:border-b-0">
              <span className="text-blue-600">→</span> {thought}
            </div>
          ))
        )}

        {isLoading && (
          <div className="text-blue-600 animate-pulse">
            <span>🤔 Thinking...</span>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-500 mt-2">
        {thoughts.length} messages • Auto-scrolling enabled
      </p>
    </div>
  );
};
