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
 * Пример:
 *   const startRun = useStartRun(dealId);
 *   startRun.mutate({ profile: "base", force_reclassify: true });
 */
export function useStartRun(dealId: string) {
  return useMutation({
    mutationFn: (data: RunCreateInput) => runApi.start(dealId, data),
  });
}

/**
 * Хук для получения информации о run.
 * Пример:
 *   const { data, isLoading } = useRun(runId, true);
 * where `true` = includeClassificationStats.
 */
export function useRun(runId: string | null, includeClassificationStats = false) {
  return useQuery({
    queryKey: ["run", runId, includeClassificationStats],
    queryFn: () => runApi.get(runId!, includeClassificationStats),
    enabled: !!runId,
  });
}

/**
 * Хук для получения отчёта по классификации.
 * Пример:
 *   const { data } = useClassificationReport(latestRunId);
 */
export function useClassificationReport(runId: string | null) {
  return useQuery({
    queryKey: ["classification-report", runId],
    queryFn: () => runApi.getClassificationReport(runId!),
    enabled: !!runId,
    staleTime: 10 * 60_000, // 10 минут — отчёт не меняется часто
  });
}
