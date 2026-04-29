/**
 * API-функции для экспорта.
 *
 * Backend endpoints:
 *   POST /api/v1/runs/{run_id}/export  — запросить экспорт
 *   GET  /api/v1/exports/{export_id}   — статус + download URL
 *
 * Контракт тела запроса:
 *   ExportRequest (backend):
 *   {
 *     export_type: string,
 *     requested_by?: string | null,
 *     requester_role?: string | null,
 *   }
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type { ExportRecord, ExportStatus, ExportType } from "../types/exports";

/* =========================
 * Константы и helpers
 * ========================= */

const EXPORT_STATUS_POLL_INTERVAL_MS = 2000 as const;

export const exportQueryKeys = {
  all: ["export"] as const,
  detail: (exportId: string | null) => ["export", exportId] as const,
};

export interface RequestExportPayload {
  runId: string;
  exportType: ExportType;
}

export function isExportProcessing(
  status: ExportStatus | null | undefined
): boolean {
  return status === "pending" || status === "processing";
}

export function isExportFinished(
  status: ExportStatus | null | undefined
): boolean {
  return status === "completed" || status === "failed";
}

export function isExportDownloadable(
  record: ExportRecord | null | undefined
): boolean {
  return record?.status === "completed" && Boolean(record.download_url);
}

// Нормализуем nullable-поля, чтобы UI мог опираться на null, а не undefined
export function normalizeExportRecord(record: ExportRecord): ExportRecord {
  return {
    ...record,
    file_ref: record.file_ref ?? null,
    file_refs: record.file_refs ?? null,
    requested_by: record.requested_by ?? null,
    requester_role: record.requester_role ?? null,
    file_size_bytes:
      typeof record.file_size_bytes === "number" ? record.file_size_bytes : null,
    created_at: record.created_at ?? null,
    updated_at: record.updated_at ?? null,
    download_url: record.download_url ?? null,
    error_message: record.error_message ?? null,
  };
}

/* =========================
 * API слой
 * ========================= */

export const exportsApi = {
  /**
   * Запросить экспорт для конкретного run.
   * Возвращает запись ExportRecord в состоянии pending/processing.
   */
  request: async (
    runId: string,
    exportType: ExportType
  ): Promise<ExportRecord> => {
    const response = await client.post<ExportRecord>(
      `/api/v1/runs/${runId}/export`,
      {
        export_type: exportType,
        // requested_by / requester_role можно будет добавить,
        // когда появится реальная авторизация.
      }
    );

    return normalizeExportRecord(response.data);
  },

  /**
   * Получить статус конкретного экспорта.
   */
  get: async (exportId: string): Promise<ExportRecord> => {
    const response = await client.get<ExportRecord>(`/api/v1/exports/${exportId}`);
    return normalizeExportRecord(response.data);
  },
};

/* =========================
 * React Query hooks
 * ========================= */

/**
 * Хук для запуска экспорта.
 *
 * - принимает runId и exportType
 * - после успеха кладёт ExportRecord в кэш, чтобы useExportStatus
 *   мог сразу использовать его как initial data.
 */
export function useRequestExport() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, exportType }: RequestExportPayload) =>
      exportsApi.request(runId, exportType),

    onSuccess: (data) => {
      qc.setQueryData(exportQueryKeys.detail(data.id), data);
    },
  });
}

/**
 * Хук статуса экспорта с polling.
 *
 * Поведение:
 * - запросы идут только если exportId задан (enabled);
 * - пока status = pending / processing — polling каждые 2 секунды;
 * - при status = completed / failed — polling останавливается;
 * - при HTTP-ошибке — polling останавливается, error доступен в UI.
 */
export function useExportStatus(exportId: string | null) {
  return useQuery({
    queryKey: exportQueryKeys.detail(exportId),
    queryFn: () => exportsApi.get(exportId!),
    enabled: Boolean(exportId),
    retry: false,
    staleTime: 0,
    refetchInterval: (query) => {
      if (query.state.status === "error") {
        return false;
      }

      const data = query.state.data as ExportRecord | undefined;

      if (!data) {
        return EXPORT_STATUS_POLL_INTERVAL_MS;
      }

      return isExportProcessing(data.status)
        ? EXPORT_STATUS_POLL_INTERVAL_MS
        : false;
    },
  });
}




