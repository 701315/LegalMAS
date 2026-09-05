// =============================================================
// src/hooks/useSSE.ts
// Hook for subscribing to analysis run progress Server-Sent Events (SSE).
//
// Production notes:
// - Automatically closes EventSource upon receiving terminal run status;
// - Does not rely solely on backend-side socket teardown;
// - Prevents built-in EventSource reconnect loops after terminal payload.
// =============================================================

import { useEffect, useRef, useState } from "react";
import type { ProgressEvent, RunStatus } from "../types";

interface UseSSEOptions {
  /** Enable or disable SSE subscription */
  enabled?: boolean;
}

/**
 * Terminal Run statuses after which SSE progress events are no longer emitted.
 * Closes the client-side connection to avoid redundant reconnect loops.
 */
function isTerminalRunStatus(status: RunStatus | null | undefined): boolean {
  return (
    status === "completed" ||
    status === "completed_with_errors" ||
    status === "failed"
  );
}

/**
 * Subscribes to SSE progress events for a specific run_id.
 *
 * Endpoint:
 *   GET /api/v1/runs/{run_id}/events
 */
export function useSSEProgress(
  runId: string | null,
  options: UseSSEOptions = {},
) {
  const { enabled = true } = options;

  const [lastEvent, setLastEvent] = useState<ProgressEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Preserve terminal completion state across renders
  const terminalSeenRef = useRef(false);

  // Reset flag when runId changes (new run, fresh subscription)
  useEffect(() => {
    terminalSeenRef.current = false;
  }, [runId]);

  useEffect(() => {
    if (!runId || !enabled || terminalSeenRef.current) {
      if (!runId || terminalSeenRef.current) {
        setLastEvent(null);
        setIsConnected(false);
        setError(null);
      }
      return;
    }

    const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const url = `${baseUrl}/api/v1/runs/${runId}/events`;

    const es = new EventSource(url);

    /**
     * Local flag to distinguish clean terminal closures from network dropouts.
     */
    let closedByTerminalEvent = false;

    es.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ProgressEvent;
        setLastEvent(data);
        setIsConnected(true);
        setError(null);

        // Terminal status reached: close EventSource immediately
        if (isTerminalRunStatus(data.status)) {
          closedByTerminalEvent = true;
          terminalSeenRef.current = true;
          setIsConnected(false);
          setError(null);
          es.close();
        }
      } catch (e) {
        console.error("Failed to parse SSE event payload", e);
      }
    };

    es.onerror = () => {
      if (closedByTerminalEvent || terminalSeenRef.current) {
        setIsConnected(false);
        setError(null);
        es.close();
        return;
      }

      setIsConnected(false);
      setError("SSE connection temporarily unavailable");
    };

    return () => {
      closedByTerminalEvent = true;
      es.close();
    };
  }, [runId, enabled]);

  return { lastEvent, isConnected, error };
}


