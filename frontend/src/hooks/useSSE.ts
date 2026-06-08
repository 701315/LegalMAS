// =============================================================
// src/hooks/useSSE.ts
// Хук для подписки на SSE-события прогресса анализа (run).
//
// Production notes:
// - автоматически закрывает EventSource на terminal run status;
// - не полагается только на backend-side close соединения;
// - не даёт встроенному reconnect EventSource бесконечно переподключаться
//   после run_progress_final / terminal payload.
// =============================================================

import { useEffect, useRef, useState } from "react";
import type { ProgressEvent, RunStatus } from "../types";

interface UseSSEOptions {
  /** Включать/отключать подписку */
  enabled?: boolean;
}

/**
 * Terminal статусы Run, после которых SSE больше не нужен.
 *
 * Для непрофессионального программиста:
 * Если анализ уже закончился, то слушать "живой" прогресс бессмысленно.
 * Наоборот, продолжение SSE после terminal status приводит к бесконечным
 * reconnect'ам EventSource и шуму в логах backend.
 */
function isTerminalRunStatus(status: RunStatus | null | undefined): boolean {
  return (
    status === "completed" ||
    status === "completed_with_errors" ||
    status === "failed"
  );
}

/**
 * Простой хук для подписки на SSE по конкретному run_id.
 *
 * Ожидается endpoint:
 *   GET /api/v1/runs/{run_id}/events
 *
 * Поддерживаем оба варианта payload:
 *   { run_id, status, completed_checks, total_checks }
 *   { run_id, status, completed, total }
 */
export function useSSEProgress(
  runId: string | null,
  options: UseSSEOptions = {},
) {
  const { enabled = true } = options;

  const [lastEvent, setLastEvent] = useState<ProgressEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Запоминаем terminal completion между рендерами.
  // useRef живёт весь lifecycle компонента, в отличие от локальной переменной effect.
  // Это предотвращает повторный connect после terminal event при ре-рендере компонента.
  const terminalSeenRef = useRef(false);

  // Сбрасываем флаг при смене runId — новый run, новая подписка.
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
     * Локальный флаг, чтобы отличать:
     * - штатное закрытие по terminal event
     * от
     * - реальной сетевой ошибки, где reconnect полезен.
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

        // Как только run перешёл в terminal status, SSE больше не нужен.
        // Закрываем EventSource на клиенте, чтобы встроенный reconnect
        // не создавал бесконечные повторные GET /events.
        if (isTerminalRunStatus(data.status)) {
          closedByTerminalEvent = true;
          terminalSeenRef.current = true;
          setIsConnected(false);
          setError(null);
          es.close();
        }
      } catch (e) {
        console.error("Ошибка парсинга SSE события", e);
      }
    };

    es.onerror = () => {
      // Если сами закрыли соединение после terminal event,
      // не переводим UI в error-state и не считаем это проблемой.
      if (closedByTerminalEvent || terminalSeenRef.current) {
        setIsConnected(false);
        setError(null);
        // Принудительно закрываем EventSource, чтобы browser native reconnect
        // не переоткрывал соединение после штатного завершения.
        es.close();
        return;
      }

      setIsConnected(false);
      setError("SSE подключение временно недоступно");
      // ВАЖНО:
      // не закрываем es здесь при реальной сетевой ошибке,
      // чтобы не ломать встроенный reconnect EventSource.
    };

    return () => {
      closedByTerminalEvent = true;
      es.close();
    };
  }, [runId, enabled]);

  return { lastEvent, isConnected, error };
}


