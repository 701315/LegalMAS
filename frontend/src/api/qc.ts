// =============================================================
// src/api/qc.ts
// QC API: review-only mode для DD Matrix.
//
// После завершения Phase 9 legacy QC API (CheckResult[]-флоу) удалён.
// Здесь остался только review-aware QC контракт:
//   POST /api/v1/qc/review        — single finding QC update
//   POST /api/v1/qc/review/bulk   — bulk findings QC update
//
// Префикс путей:
// - axios baseURL = http://localhost:8000 (без /api/v1),
//   поэтому в каждом пути префикс /api/v1 указан явно.
// =============================================================

import { useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import { dealReviewKeys } from "./dealReview";
import type { ReviewQcStatus } from "../types/dealReview";

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
    client
      .post<ReviewQCUpdateResponse>("/api/v1/qc/review", payload)
      .then((r) => r.data),

  /**
   * Применить QC-действие к нескольким finding'ам review matrix.
   * POST /api/v1/qc/review/bulk
   */
  bulkUpdateReviewQc: (payload: ReviewQCBulkUpdateRequest) =>
    client
      .post<ReviewQCBulkUpdateResponse>("/api/v1/qc/review/bulk", payload)
      .then((r) => r.data),
};

// ===== Review React Query mutations =====

/**
 * Хук для QC-действия над одной review-ячейкой.
 *
 * После успеха инвалидируем review dd-matrix query,
 * чтобы UI перечитал обновлённый single source of truth.
 */
export function useUpdateReviewQc() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: reviewQcApi.updateReviewQc,
    onSuccess: async (data) => {
      await qc.invalidateQueries({
        queryKey: dealReviewKeys.ddMatrix(data.deal_id, data.run_id),
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
        queryKey: dealReviewKeys.ddMatrix(data.deal_id, data.run_id),
      });
    },
  });
}


