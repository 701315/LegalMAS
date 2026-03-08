// =============================================================
// src/api/importJobs.ts
// API-функции и React Query-хук для статуса импорта документов.
// =============================================================

import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type { ImportJob } from "../types";

/**
 * Низкоуровневая функция: получить статус ImportJob по job_id.
 * Ожидается, что бэкенд реализует:
 *   GET /api/v1/import-jobs/{job_id}
 * и возвращает объект, совместимый с типом ImportJob.
 */
export const importJobApi = {
  get: (jobId: string) =>
    client
      .get<ImportJob>(`/api/v1/import-jobs/${jobId}`)
      .then((res) => res.data),
};

/**
 * React Query-хук для поллинга статуса ImportJob.
 *
 * Пример использования:
 *   const { data, isFetching } = useImportJob(jobId, true);
 *
 * enablePolling = true — опрос каждые 2 секунды.
 * Остановку по status === "completed"/"failed" можно делать на уровне компонента.
 */
export function useImportJob(jobId: string | null, enablePolling = false) {
  return useQuery({
    queryKey: ["import-job", jobId],
    queryFn: () => importJobApi.get(jobId!),
    enabled: !!jobId,
    refetchInterval: enablePolling ? 2000 : false,
    refetchIntervalInBackground: true,
  });
}
