/**
 * useAsync - Generic hook for handling async operations
 * Returns loading, error, and data states
 */

import { useState, useCallback, useEffect } from 'react';

type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'pending' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };

export const useAsync = <T,>(
  asyncFunction: () => Promise<T>,
  immediate = true,
  deps?: any[]
) => {
  const [state, setState] = useState<AsyncState<T>>({ status: 'idle' });

  const execute = useCallback(async () => {
    setState({ status: 'pending' });
    try {
      const response = await asyncFunction();
      setState({ status: 'success', data: response });
      return response;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      setState({ status: 'error', error: err });
      throw err;
    }
  }, [asyncFunction]);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [execute, immediate, ...(deps || [])]);

  return {
    execute,
    status: state.status,
    data: state.status === 'success' ? state.data : undefined,
    error: state.status === 'error' ? state.error : undefined,
    isLoading: state.status === 'pending',
    isSuccess: state.status === 'success',
    isError: state.status === 'error',
  };
};
