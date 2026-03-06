/**
 * API-функции для экспорта.
 *
 * Backend endpoints:
 *   POST /api/v1/runs/{run_id}/export  — запросить экспорт
 *   GET  /api/v1/exports/{export_id}   — статус + download URL
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type { ExportRecord } from "../types";

export const exportsApi = {
  /** Запросить экспорт. */
  request: (runId: string, exportType: string) =>
    client
      .post<ExportRecord>(`/api/v1/runs/${runId}/export`, {
        export_type: exportType,
      })
      .then((r) => r.data),

  /** Статус экспорта + URL для скачивания. */
  get: (exportId: string) =>
    client
      .get<ExportRecord>(`/api/v1/exports/${exportId}`)
      .then((r) => r.data),
};

// ===== React Query хуки =====

/** Запросить генерацию экспорта. */
export function useRequestExport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      exportType,
    }: {
      runId: string;
      exportType: string;
    }) => exportsApi.request(runId, exportType),
    onSuccess: (data) =>
      qc.setQueryData(["export", data.id], data),
  });
}

/**
 * Статус экспорта с автоматическим polling.
 *
 * Пока status === "processing" — опрашивает каждые 2 секунды.
 * Когда готов — прекращает опрос.
 */
export function useExportStatus(exportId: string | null) {
  return useQuery({
    queryKey: ["export", exportId],
    queryFn: () => exportsApi.get(exportId!),
    enabled: !!exportId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || data.status === "processing") return 2000;
      return false;
    },
  });
}
