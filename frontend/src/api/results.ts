// =============================================================
// src/api/results.ts
// API-функции и React-хуки для DD-результатов и запусков (runs).
// =============================================================

import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type { CheckResult, Run, PaginatedResponse } from "../types";

/**
 * Параметры фильтрации списка результатов на бэкенде.
 * Пока будем использовать только часть из них, но тип сразу "запасной".
 */
export interface ResultsFilter {
  page?: number;
  per_page?: number;
  doc_type?: string;
  severity?: string;
  conditional_only?: boolean;
}

/**
 * Обёртка над HTTP-запросами к backend для результатов DD.
 */
export const resultApi = {
  /**
   * Список результатов для одного run (постранично).
   * GET /api/v1/runs/{run_id}/results
   */
  list: (runId: string, params?: ResultsFilter) =>
    client
      .get<PaginatedResponse<CheckResult>>(
        `/api/v1/runs/${runId}/results`,
        {
          params: {
            page: params?.page ?? 1,
            per_page: params?.per_page ?? 200,
            ...(params?.doc_type && { doc_type: params.doc_type }),
            ...(params?.severity && { severity: params.severity }),
            ...(params?.conditional_only && {
              conditional_only: true,
            }),
          },
        },
      )
      .then((r) => r.data),

  /**
   * Один результат по ID.
   * GET /api/v1/results/{result_id}
   */
  get: (resultId: string) =>
    client
      .get<CheckResult>(`/api/v1/results/${resultId}`)
      .then((r) => r.data),

      
  /**
   * Список запусков для сделки.
   * GET /api/v1/runs/deal/{deal_id}
   */
  listRuns: (dealId: string, includeStats = false) =>
    client
      .get<Run[]>(`/api/v1/runs/deal/${dealId}`, {
        params: includeStats
          ? { include_classification_stats: true }
          : {},
      })
      .then((r) => r.data),

};

/**
 * Хук, который загружает ВСЕ результаты для одного run.
 *
 * На первом этапе мы делаем простую версию:
 * - запрашиваем одну страницу (до 200–500 записей);
 * - если нужно будет больше, легко расширим до "загрузить все страницы".
 */
export function useAllResults(runId: string | null) {
  return useQuery({
    queryKey: ["all-results", runId],
    queryFn: async () => {
      if (!runId) return [];

      const firstPage = await resultApi.list(runId, {
        page: 1,
        per_page: 500, // можно подстроить под реальные объёмы
      });

      // Пока просто возвращаем items первой страницы.
      // При необходимости расширим до загрузки всех страниц.
      return firstPage.items;
    },
    enabled: !!runId,
    staleTime: 5 * 60_000, // 5 минут кэша
  });
}

/**
 * Хук для получения "последнего" run по сделке.
 * Предполагаем, что backend отдаёт runs в порядке "новые сначала".
 */
export function useLatestRun(dealId: string | null, includeStats = true) {
  return useQuery({
    queryKey: ["latest-run", dealId, includeStats],
    queryFn: async () => {
      if (!dealId) return null;

      const runs = await resultApi.listRuns(dealId, includeStats);
      return runs.length > 0 ? runs[0] : null;
    },
    enabled: !!dealId,
  });
}
