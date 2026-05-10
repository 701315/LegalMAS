// =============================================================
// src/pages/tabs/grid/reviewGrid.qc.ts
// QC-помощники для review-only режима DD Grid.
//
// Для непрофессионального программиста:
// Этот файл описывает, как review grid готовит выбранные строки
// к возможному QC-процессу.
//
// ВАЖНО:
// - selection в review grid сейчас row-level, то есть пользователь выбирает
//   строки матрицы, а не отдельные findings;
// - backend QC API LegalMAS пока принимает только legacy result_ids;
// - review matrix backend DTO не содержит result_id,
//   поэтому прямой bulk QC для review mode пока недоступен.
// =============================================================

import type { ReviewFinding, ReviewSelectionItem } from "./reviewGrid.types";

/**
 * Причина, почему текущую review selection пока нельзя отправить в QC API.
 *
 * Для непрофессионального программиста:
 * Сейчас причина только одна — backend ждёт legacy result_ids,
 * а в review DTO таких идентификаторов нет.
 */
export type ReviewQcUnsupportedReason = "missing_legacy_result_ids";

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
 * Нормализованная строка выборки для будущего review-QC API.
 *
 * Для непрофессионального программиста:
 * Это не payload для текущего backend.
 * Это аккуратная промежуточная структура, которую можно будет
 * использовать в будущем review-specific endpoint.
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
 * Возвращает findings, которые относятся к выбранным строкам review matrix.
 *
 * Для непрофессионального программиста:
 * Одна выбранная строка матрицы может содержать несколько findings.
 * Поэтому функция возвращает не одну запись на строку,
 * а все findings, принадлежащие выбранным rowId.
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
 * Для непрофессионального программиста:
 * Эта функция нужна не для текущего legacy QC API,
 * а для будущего review-specific QC API.
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
 * Для непрофессионального программиста:
 * Сейчас ответ всегда "нет", потому что backend QC API принимает только
 * legacy result_ids из старой модели CheckResult[],
 * а review DTO таких id не содержит.
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
      "QC для review-матрицы пока недоступен: backend QC API принимает только legacy result_ids, а review DTO их не содержит.",
  };
}

/**
 * Возвращает поясняющий текст для disabled-state в UI.
 */
export function getReviewQcDisabledNote(
  selection: ReviewSelectionItem[],
): string {
  return getReviewQcCapability(selection).message;
}


