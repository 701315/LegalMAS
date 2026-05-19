// =============================================================
// src/api/runs.ts
// API-функции и React Query хуки для запусков анализа (runs).
//
// Архитектурный принцип:
// - run state адресуется только по конкретному runId;
// - current run для сделки определяется вне этого файла через deal.last_run_id;
// - этот файл отвечает за:
//   1) старт run,
//   2) чтение конкретного run,
//   3) чтение истории run'ов сделки,
//   4) чтение classification report для конкретного run.
// =============================================================

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import { documentKeys } from "./documents";
import type { ClassificationReport, Run, RunCreateInput } from "../types";

const RUN_POLL_INTERVAL_MS = 2000;
const RUN_HISTORY_STALE_TIME_MS = 2 * 60_000;
const CLASSIFICATION_REPORT_STALE_TIME_MS = 10 * 60_000;

function isTerminalRunStatus(status: Run["status"] | undefined): boolean {
  return (
    status === "completed" ||
    status === "completed_with_errors" ||
    status === "failed"
  );
}

/**
 * Единая фабрика query keys для runs.
 * Важно:
 * - detail адресуется по runId;
 * - history адресуется по dealId;
 * - classificationReport адресуется по runId.
 */
export const runKeys = {
  all: ["runs"] as const,

  history: (dealId: string, includeClassificationStats = false) =>
    ["runs", "history", dealId, includeClassificationStats] as const,

  detail: (runId: string, includeClassificationStats = false) =>
    ["runs", "detail", runId, includeClassificationStats] as const,

  classificationReport: (runId: string) =>
    ["runs", "classification-report", runId] as const,
};

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
   * Получение информации о конкретном run.
   * GET /api/v1/runs/{run_id}
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
   * История запусков по сделке.
   * Ранее это жило в resultApi.listDealRuns(...),
   * но семантически это API запусков, поэтому переносим сюда.
   *
   * Предполагаемый endpoint:
   * GET /api/v1/deals/{deal_id}/runs
   */
  listDealRuns: (dealId: string, includeClassificationStats = false) =>
    client
      .get<Run[]>(`/api/v1/deals/${dealId}/runs`, {
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
        qc.invalidateQueries({ queryKey: documentKeys.byDeal(dealId) }),
        qc.invalidateQueries({ queryKey: runKeys.history(dealId, false) }),
        qc.invalidateQueries({ queryKey: runKeys.history(dealId, true) }),
      ]);
    },
  });
}

/**
 * Хук для чтения истории запусков по сделке.
 * Используется, например, в Overview timeline.
 */
export function useDealRuns(
  dealId: string,
  includeClassificationStats = false,
) {
  const enabled = !!dealId;

  return useQuery<Run[], Error>({
    queryKey: runKeys.history(dealId, includeClassificationStats),
    queryFn: () => {
      if (!enabled) {
        throw new Error("dealId is required to fetch deal runs");
      }
      return runApi.listDealRuns(dealId, includeClassificationStats);
    },
    enabled,
    staleTime: RUN_HISTORY_STALE_TIME_MS,
    refetchOnWindowFocus: true,
  });
}

/**
 * Хук для получения информации о конкретном run.
 */
export function useRun(
  runId: string | null,
  includeClassificationStats = false,
) {
  const enabled = !!runId;

  return useQuery<Run, Error>({
    queryKey: runId
      ? runKeys.detail(runId, includeClassificationStats)
      : ["runs", "detail", "disabled", includeClassificationStats],
    queryFn: () => {
      if (!runId) {
        throw new Error("runId is required to fetch run details");
      }
      return runApi.get(runId, includeClassificationStats);
    },
    enabled,
    staleTime: 1000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!enabled) {
        return false;
      }
      if (!data) {
        return RUN_POLL_INTERVAL_MS;
      }
      if (isTerminalRunStatus(data.status)) {
        return false;
      }
      return RUN_POLL_INTERVAL_MS;
    },
  });
}

/**
 * Хук для получения отчёта по классификации конкретного run.
 */
export function useClassificationReport(runId: string | null) {
  const enabled = !!runId;

  return useQuery<ClassificationReport, Error>({
    queryKey: runId
      ? runKeys.classificationReport(runId)
      : ["runs", "classification-report", "disabled"],
    queryFn: () => {
      if (!runId) {
        throw new Error("runId is required to fetch classification report");
      }
      return runApi.getClassificationReport(runId);
    },
    enabled,
    staleTime: CLASSIFICATION_REPORT_STALE_TIME_MS,
    refetchOnWindowFocus: false,
  });
}



