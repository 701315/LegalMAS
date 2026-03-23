// =============================================================
// src/api/runs.ts
// API-функции и React Query хуки для запусков анализа (runs).
// =============================================================

import { useQuery, useMutation } from "@tanstack/react-query";
import client from "./client";
import type { Run, RunCreateInput, ClassificationReport } from "../types";

// -------------------------------------------------------------
// НИЗКОУРОВНЕВЫЙ API-КЛИЕНТ
// -------------------------------------------------------------

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
  return useMutation({
    mutationFn: (data: RunCreateInput) => runApi.start(dealId, data),
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
    // Здесь query — это Query<Run | null, Error, ...>
    refetchInterval: (query) => {
      const data = query.state.data as Run | null;
      if (!data) return false;
      if (data.status === "running" || data.status === "pending") return 2000;
      return false;
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
    staleTime: 10 * 60_000, // 10 минут — отчёт не меняется часто
  });
}
