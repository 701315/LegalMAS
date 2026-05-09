// =============================================================
// src/api/qc.ts
// QC API: legacy + review modes.
//
// ВАЖНО:
// - legacy section используется старым DD Grid и CheckResult[]-флоу;
// - review section используется новым DD Matrix / review-only UI;
// - после завершения Фазы 9 legacy section будет удалён.
// =============================================================

import { useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type { CheckResult } from "../types";
import type { ReviewQcStatus } from "../types/dealReview";

// -------------------------------------------------------------
// LEGACY QC API
// -------------------------------------------------------------

/**
 * Общий тип ответа legacy QC-эндпоинтов.
 * В текущем контракте backend возвращает обновлённые CheckResult[].
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

// ===== Legacy React Query mutations =====

/**
 * Хук для подтверждения legacy результатов.
 * Пример:
 * const confirm = useConfirmResults();
 * await confirm.mutateAsync({ ids: ["id1", "id2"], comment: "Ок" });
 */
export function useConfirmResults() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ ids, comment }: { ids: string[]; comment?: string }) =>
      qcApi.confirm(ids, comment),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["all-results"] });
    },
  });
}

/**
 * Хук для отклонения legacy результатов.
 */
export function useRejectResults() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ ids, comment }: { ids: string[]; comment?: string }) =>
      qcApi.reject(ids, comment),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["all-results"] });
    },
  });
}

/**
 * Хук для legacy override (смена severity и, при желании, результата).
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
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["all-results"] });
    },
  });
}

// -------------------------------------------------------------
// REVIEW QC API
// -------------------------------------------------------------

/**
 * Ключ одной review-ячейки/finding.
 * Совпадает с backend-схемой ReviewFindingKey.
 */
export interface ReviewFindingKey {
  run_id: string;
  document_id: string;
  check_id: string;
  segment_id?: string | null;
}

/**
 * Одиночный review QC update.
 * Совпадает с backend-схемой ReviewQCUpdateRequest.
 */
export interface ReviewQCUpdateRequest {
  finding: ReviewFindingKey;
  qc_status: ReviewQcStatus;
  comment?: string | null;
}

/**
 * Ответ на одиночный review QC update.
 * Совпадает с backend-схемой ReviewQCUpdateResponse.
 */
export interface ReviewQCUpdateResponse {
  run_id: string;
  deal_id: string;
  document_id: string;
  check_id: string;
  segment_id?: string | null;
  qc_status: string;
  qc_by: string;
  qc_at: string | null;
  qc_comment: string | null;
  updated_rows_count: number;
}

/**
 * Массовый review QC update.
 * Совпадает с backend-схемой ReviewQCBulkUpdateRequest.
 */
export interface ReviewQCBulkUpdateRequest {
  findings: ReviewFindingKey[];
  qc_status: ReviewQcStatus;
  comment?: string | null;
}

/**
 * Ответ по одному finding внутри bulk review update.
 */
export interface ReviewQCBulkItemResponse {
  run_id: string;
  deal_id: string;
  document_id: string;
  check_id: string;
  segment_id?: string | null;
  qc_status: string;
  qc_by: string;
  qc_at: string | null;
  qc_comment: string | null;
  updated_rows_count: number;
}

/**
 * Ответ на bulk review QC update.
 * Совпадает с backend-схемой ReviewQCBulkUpdateResponse.
 */
export interface ReviewQCBulkUpdateResponse {
  run_id: string;
  deal_id: string;
  qc_status: string;
  qc_by: string;
  qc_at: string | null;
  qc_comment: string | null;
  total_findings: number;
  updated_findings: number;
  changed_findings: number;
  updated_rows_count: number;
  items: ReviewQCBulkItemResponse[];
}

export const reviewQcApi = {
  /**
   * Применить QC-действие к одному finding'у review matrix.
   * POST /api/v1/qc/review
   */
  updateReviewQc: (payload: ReviewQCUpdateRequest) =>
    client.post<ReviewQCUpdateResponse>("/qc/review", payload).then((r) => r.data),

  /**
   * Применить QC-действие к нескольким finding'ам review matrix.
   * POST /api/v1/qc/review/bulk
   */
  bulkUpdateReviewQc: (payload: ReviewQCBulkUpdateRequest) =>
    client
      .post<ReviewQCBulkUpdateResponse>("/qc/review/bulk", payload)
      .then((r) => r.data),
};

// ===== Review React Query mutations =====

/**
 * Хук для QC-действия над одной review-ячейкой.
 *
 * ВАЖНО:
 * После успеха инвалидируем review dd-matrix query,
 * чтобы UI перечитал обновлённый single source of truth.
 */
export function useUpdateReviewQc() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: reviewQcApi.updateReviewQc,
    onSuccess: async (data) => {
      await qc.invalidateQueries({
        queryKey: ["deal-review", "dd-matrix", data.deal_id, data.run_id],
      });
    },
  });
}

/**
 * Хук для массового QC-действия в review mode.
 */
export function useBulkUpdateReviewQc() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: reviewQcApi.bulkUpdateReviewQc,
    onSuccess: async (data) => {
      await qc.invalidateQueries({
        queryKey: ["deal-review", "dd-matrix", data.deal_id, data.run_id],
      });
    },
  });
}


