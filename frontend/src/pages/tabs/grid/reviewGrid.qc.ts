// =============================================================
// src/pages/tabs/grid/reviewGrid.qc.ts
// QC-помощники для review-only режима DD Grid.
// ВАЖНО:
// Текущий QC API LegalMAS принимает только legacy result_ids.
// В review matrix backend DTO не содержит result_id, поэтому
// прямой bulk QC для review-mode пока недоступен без backend support.
// =============================================================

import type { ReviewFinding, ReviewSelectionItem } from "./reviewGrid.types";

/**
 * Тип причины, почему review selection пока нельзя отправить в legacy QC API.
 */
export type ReviewQcUnsupportedReason =
  | "missing_legacy_result_ids"
  | "review_api_not_implemented";

/**
 * Итог проверки возможности QC по текущему review selection.
 */
export interface ReviewQcCapability {
  supported: boolean;
  reason: ReviewQcUnsupportedReason | null;
  message: string;
  selectedCount: number;
}

/**
 * Строка выборки для будущего review-QC API.
 *
 * ВАЖНО:
 * - selection в review grid сейчас row-level;
 * - поэтому QC targets строятся из findings, принадлежащих выбранным rows.
 */
export interface ReviewQcTarget {
  findingId: string;
  rowId: string;

  documentId: string;
  documentName: string;

  checkId: string;
  checkName: string;

  segmentId?: string | null;
  chunkId?: string | null;
  chunkIndex?: number | null;

  result: string;
  severity?: string | null;
  qcStatus?: string | null;
}

/**
 * Возвращает выбранные findings по row-level selection item list.
 *
 * ВАЖНО:
 * - review selection сейчас хранит rowId, а не findingId;
 * - выбранная строка матрицы может содержать несколько findings;
 * - поэтому функция возвращает все findings выбранных rows.
 */
export function getSelectedReviewFindings(
  findings: ReviewFinding[],
  selection: ReviewSelectionItem[],
): ReviewFinding[] {
  if (!selection.length || !findings.length) {
    return [];
  }

  const selectedRowIds = new Set(selection.map((item) => item.rowId));
  return findings.filter((finding) => selectedRowIds.has(finding.rowId));
}

/**
 * Преобразует findings в нормализованный список review QC targets.
 *
 * Эта функция подготавливает selection-derived findings
 * к будущему review-specific QC endpoint.
 */
export function buildReviewQcTargets(
  findings: ReviewFinding[],
): ReviewQcTarget[] {
  return findings.map((finding) => ({
    findingId: finding.findingId,
    rowId: finding.rowId,

    documentId: finding.documentId,
    documentName: finding.documentName,

    checkId: finding.checkId,
    checkName: finding.checkName,

    segmentId: finding.segmentId ?? null,
    chunkId: finding.chunkId ?? null,
    chunkIndex: finding.chunkIndex ?? null,

    result: finding.result,
    severity: finding.severity ?? null,
    qcStatus: finding.qcStatus ?? null,
  }));
}

/**
 * Проверяет, можно ли текущую review selection отправить в QC.
 *
 * Сейчас ответ всегда "нет", потому что backend QC API принимает только
 * result_ids из legacy CheckResult[], а review DTO таких id не содержит.
 */
export function getReviewQcCapability(
  selection: ReviewSelectionItem[],
): ReviewQcCapability {
  if (!selection.length) {
    return {
      supported: false,
      reason: "missing_legacy_result_ids",
      message: "Не выбраны строки review-матрицы для QC.",
      selectedCount: 0,
    };
  }

  return {
    supported: false,
    reason: "missing_legacy_result_ids",
    selectedCount: selection.length,
    message:
      "QC для review-матрицы пока недоступен: выборка в review mode работает на уровне строк матрицы, а backend QC API принимает только legacy result_ids, которых в review DTO нет.",
  };
}

/**
 * Возвращает текст для disabled-state / helper note в UI.
 */
export function getReviewQcDisabledNote(
  selection: ReviewSelectionItem[],
): string {
  const capability = getReviewQcCapability(selection);
  return capability.message;
}



