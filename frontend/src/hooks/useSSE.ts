// =============================================================
// src/hooks/useSSE.ts
// Хук для подписки на SSE-события прогресса анализа (run).
// =============================================================

import { useEffect, useState } from "react";
import type { ProgressEvent } from "../types";

interface UseSSEOptions {
  /** Включать/отключать подписку */
  enabled?: boolean;
}

/**
 * Простой хук для подписки на SSE по конкретному run_id.
 *
 * Ожидается, что на бэкенде есть endpoint:
 *   GET /api/v1/runs/{run_id}/events
 * который шлёт события в формате JSON:
 *   { "run_id": "...", "status": "...", "completed_checks": 10, ... }
 */
export function useSSEProgress(
  runId: string | null,
  options: UseSSEOptions = {},
) {
  const { enabled = true } = options;

  const [lastEvent, setLastEvent] = useState<ProgressEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId || !enabled) {
      return;
    }

    // Формируем URL SSE-эндпоинта
    const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const url = `${baseUrl}/api/v1/runs/${runId}/events`;

    const es = new EventSource(url);

    es.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ProgressEvent;
        setLastEvent(data);
      } catch (e) {
        console.error("Ошибка парсинга SSE события", e);
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      setError("SSE подключение прервано");
      es.close();
    };

    // Очистка при размонтировании
    return () => {
      es.close();
    };
  }, [runId, enabled]);

  return { lastEvent, isConnected, error };
}
