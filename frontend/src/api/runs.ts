// =============================================================
// src/api/runs.ts
// API-функции и React Query хуки для запусков анализа (runs).
// =============================================================

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type { ClassificationReport, Run, RunCreateInput } from "../types";

// -------------------------------------------------------------
// НИЗКОУРОВНЕВЫЙ API-КЛИЕНТ
// -------------------------------------------------------------

const RUN_POLL_INTERVAL_MS = 2000;

function isTerminalRunStatus(status: Run["status"] | undefined): boolean {
  return (
    status === "completed" ||
    status === "completed_with_errors" ||
    status === "failed"
  );
}

export const runApi = {
  /**
   * Старт нового анализа по сделке.
   * POST /api/v1/deals/{deal_id}/run
   *
   * В body передаём RunCreateInput:
   *  - profile?: "core" | "full" | "max"
   *  - checks_mode?: "global_only" | "doc_type_only" | "global_and_doc_type"
   *  - force_reclassify?: boolean
   */
  start: (dealId: string, data: RunCreateInput) =>
    client
      .post<Run>(`/api/v1/deals/${dealId}/run`, data)
      .then((response) => response.data),

  /**
   * Получение информации о run.
   * GET /api/v1/runs/{run_id}
   *
   * Если includeClassificationStats = true,
   * добавляем параметр include_classification_stats=true,
   * чтобы бэкенд вернул classification_stats.
   */
  get: (runId: string, includeClassificationStats = false) =>
    client
      .get<Run>(`/api/v1/runs/${runId}`, {
        params: includeClassificationStats
          ? { include_classification_stats: true }
          : {},
      })
      .then((response) => response.data),

  /**
   * Отчёт по классификации для run.
   * GET /api/v1/runs/{run_id}/classification-report
   */
  getClassificationReport: (runId: string) =>
    client
      .get<ClassificationReport>(
        `/api/v1/runs/${runId}/classification-report`,
      )
      .then((response) => response.data),
};

// -------------------------------------------------------------
// REACT QUERY ХУКИ
// -------------------------------------------------------------

/**
 * Хук для старта нового run.
 */
export function useStartRun(dealId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (data: RunCreateInput) => runApi.start(dealId, data),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["deal", dealId] }),
        qc.invalidateQueries({ queryKey: ["documents-count", dealId] }),
        qc.invalidateQueries({ queryKey: ["documents", dealId] }),
      ]);
    },
  });
}

/**
 * Хук для получения информации о run.
 */
export function useRun(
  runId: string | null,
  includeClassificationStats = false,
) {
  return useQuery<Run | null, Error>({
    queryKey: ["run", runId, includeClassificationStats],
    queryFn: async () => {
      if (!runId) return null;
      return runApi.get(runId, includeClassificationStats);
    },
    enabled: !!runId,
    staleTime: 1000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    refetchInterval: (query) => {
      const data = query.state.data as Run | null;
      if (!data) return RUN_POLL_INTERVAL_MS;
      if (isTerminalRunStatus(data.status)) return false;
      return RUN_POLL_INTERVAL_MS;
    },
  });
}

/**
 * Хук для получения отчёта по классификации.
 */
export function useClassificationReport(runId: string | null) {
  return useQuery<ClassificationReport, Error>({
    queryKey: ["classification-report", runId],
    queryFn: () => runApi.getClassificationReport(runId!),
    enabled: !!runId,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
  });
}

