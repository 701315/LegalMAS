// =============================================================
// src/api/qc.ts
// API для QC-операций и React-хуки (confirm / reject / override).
// =============================================================

import { useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type { CheckResult } from "../types";

/**
 * Общий тип ответа QC-эндпоинтов.
 * В реальном API тут можно добавить более подробное тело.
 */
export interface QCResponse {
  updated_results: CheckResult[];
}

export const qcApi = {
  /**
   * Подтвердить результаты (QC: confirm).
   * POST /api/v1/qc/confirm
   */
  confirm: (resultIds: string[], comment?: string) =>
    client
      .post<QCResponse>("/qc/confirm", {
        result_ids: resultIds,
        comment,
      })
      .then((r) => r.data),

  /**
   * Отклонить результаты (QC: reject).
   * POST /api/v1/qc/reject
   */
  reject: (resultIds: string[], comment?: string) =>
    client
      .post<QCResponse>("/qc/reject", {
        result_ids: resultIds,
        comment,
      })
      .then((r) => r.data),

  /**
   * Переопределить результат (QC: override).
   * POST /api/v1/qc/override
   *
   * newSeverity — новая серьёзность (например, "critical", "high", "medium", "low").
   * newResult   — опционально новый результат: pass / fail / unclear.
   */
  override: (
    resultIds: string[],
    newSeverity: string,
    comment: string,
    newResult?: "pass" | "fail" | "unclear",
  ) =>
    client
      .post<QCResponse>("/qc/override", {
        result_ids: resultIds,
        new_severity: newSeverity,
        comment,
        ...(newResult && { new_result: newResult }),
      })
      .then((r) => r.data),
};

// ===== React Query мутации =====

/**
 * Хук для подтверждения результатов.
 * Пример использования:
 *
 * const confirm = useConfirmResults();
 * await confirm.mutateAsync({ ids: ["id1", "id2"], comment: "Ок" });
 */
export function useConfirmResults() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ ids, comment }: { ids: string[]; comment?: string }) =>
      qcApi.confirm(ids, comment),
    onSuccess: () => {
      // Грубая, но простая стратегия:
      // сказать React Query, что "all-results" устарели.
      qc.invalidateQueries({ queryKey: ["all-results"] });
    },
  });
}

/**
 * Хук для отклонения результатов.
 */
export function useRejectResults() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ ids, comment }: { ids: string[]; comment?: string }) =>
      qcApi.reject(ids, comment),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["all-results"] });
    },
  });
}

/**
 * Хук для override (смена severity и, при желании, самого результата).
 */
export function useOverrideResults() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      ids,
      newSeverity,
      comment,
      newResult,
    }: {
      ids: string[];
      newSeverity: string;
      comment: string;
      newResult?: "pass" | "fail" | "unclear";
    }) => qcApi.override(ids, newSeverity, comment, newResult),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["all-results"] });
    },
  });
}
