// =============================================================
// src/api/results.ts
// API-функции и React Query хуки для DD-результатов.
//
// Архитектурный принцип:
// - этот файл НЕ отвечает за current run;
// - этот файл НЕ читает run state;
// - этот файл работает только с результатами конкретного run
//   и отдельными result entity.
//
// Всё, что связано с runs, живёт в src/api/runs.ts.
// =============================================================

import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type { CheckResult, PaginatedResponse } from "../types";

/**
 * Параметры фильтрации списка результатов на backend.
 */
export interface ResultsFilter {
  page?: number;
  per_page?: number;
  doc_type?: string;
  severity?: string;
  conditional_only?: boolean;
  /** Если true — только результаты, где есть structured_data */
  has_structured_data?: boolean;
}

/**
 * Единая фабрика query keys для результатов.
 */
export const resultKeys = {
  all: ["results"] as const,

  list: (runId: string, params?: ResultsFilter) =>
    [
      "results",
      "list",
      runId,
      {
        page: params?.page ?? 1,
        perPage: params?.per_page ?? 200,
        docType: params?.doc_type ?? null,
        severity: params?.severity ?? null,
        conditionalOnly: params?.conditional_only ?? false,
        hasStructuredData:
          params?.has_structured_data !== undefined
            ? params.has_structured_data
            : null,
      },
    ] as const,

  detail: (resultId: string) => ["results", "detail", resultId] as const,

  allForRun: (runId: string) => ["results", "all-for-run", runId] as const,
};

/**
 * Низкоуровневый API для работы с результатами.
 */
export const resultApi = {
  /**
   * Список результатов для одного run (постранично).
   * GET /api/v1/runs/{run_id}/results
   */
  list: (runId: string, params?: ResultsFilter) =>
    client
      .get<PaginatedResponse<CheckResult>>(`/api/v1/runs/${runId}/results`, {
        params: {
          page: params?.page ?? 1,
          per_page: params?.per_page ?? 200,
          ...(params?.doc_type ? { doc_type: params.doc_type } : {}),
          ...(params?.severity ? { severity: params.severity } : {}),
          ...(params?.conditional_only ? { conditional_only: true } : {}),
          ...(params?.has_structured_data !== undefined
            ? { has_structured_data: params.has_structured_data }
            : {}),
        },
      })
      .then((response) => response.data),

  /**
   * Один результат по ID.
   * GET /api/v1/results/{result_id}
   */
  get: (resultId: string) =>
    client
      .get<CheckResult>(`/api/v1/results/${resultId}`)
      .then((response) => response.data),
};

/**
 * Хук для получения одного result по ID.
 */
export function useResult(resultId: string | null) {
  const enabled = !!resultId;

  return useQuery<CheckResult, Error>({
    queryKey: resultId
      ? resultKeys.detail(resultId)
      : ["results", "detail", "disabled"],
    queryFn: () => {
      if (!resultId) {
        throw new Error("resultId is required to fetch result details");
      }
      return resultApi.get(resultId);
    },
    enabled,
    staleTime: 5 * 60_000,
  });
}

/**
 * Хук для получения страницы результатов по run.
 */
export function useResults(
  runId: string | null,
  params?: ResultsFilter,
) {
  const enabled = !!runId;

  return useQuery<PaginatedResponse<CheckResult>, Error>({
    queryKey: runId
      ? resultKeys.list(runId, params)
      : ["results", "list", "disabled"],
    queryFn: () => {
      if (!runId) {
        throw new Error("runId is required to fetch results");
      }
      return resultApi.list(runId, params);
    },
    enabled,
    staleTime: 5 * 60_000,
  });
}

/**
 * Хук, который загружает результаты для одного run.
 *
 * Пока берём первую страницу увеличенного размера.
 * Если позже потребуется реально собирать все страницы —
 * это лучше сделать отдельной доработкой, не смешивая ответственность.
 */
export function useAllResults(runId: string | null) {
  const enabled = !!runId;

  return useQuery<CheckResult[], Error>({
    queryKey: runId
      ? resultKeys.allForRun(runId)
      : ["results", "all-for-run", "disabled"],
    queryFn: async () => {
      if (!runId) {
        throw new Error("runId is required to fetch all results");
      }

      const firstPage = await resultApi.list(runId, {
        page: 1,
        per_page: 500,
      });

      return firstPage.items;
    },
    enabled,
    staleTime: 5 * 60_000,
  });
}


