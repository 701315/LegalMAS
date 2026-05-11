// =============================================================
// src/pages/tabs/grid/reviewGrid.qc.ts
// QC-помощники для review-only режима DD Grid.
//
// Backend контракт:
//   POST /api/v1/qc/review        — single finding QC update
//   POST /api/v1/qc/review/bulk   — bulk findings QC update
//
// Все findings в bulk-операции должны принадлежать одному run_id —
// это требование backend-схемы ReviewQCBulkUpdateRequest.
// =============================================================

import type {
  ReviewFindingKey,
  ReviewQCBulkUpdateRequest,
} from "../../../api/qc";
import type { ReviewQcStatus } from "../../../types/dealReview";

import type { ReviewFinding, ReviewSelectionItem } from "./reviewGrid.types";

/**
 * Причины, по которым текущая review-selection не может быть отправлена в QC.
 */
export type ReviewQcUnsupportedReason =
  | "empty_selection"
  | "no_findings_in_selection"
  | "mixed_run_ids";

/**
 * Итог проверки возможности QC по текущему review selection.
 */
export interface ReviewQcCapability {
  supported: boolean;
  reason: ReviewQcUnsupportedReason | null;
  message: string | null;
  selectedRowsCount: number;
  selectedFindingsCount: number;
}

/**
 * Один target QC-операции: достаточно для ReviewFindingKey.
 */
export interface ReviewQcTarget {
  findingId: string;
  rowId: string;

  runId: string;
  documentId: string;
  documentName: string;

  checkId: string;
  checkName: string;

  segmentId: string | null;
  chunkId: string | null;
  chunkIndex: number | null;

  result: string;
  severity: string | null;
  qcStatus: string | null;
}

/**
 * Возвращает findings, относящиеся к выбранным строкам review matrix.
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
 * Преобразует ReviewFinding[] в нормализованный список targets.
 */
export function buildReviewQcTargets(
  findings: ReviewFinding[],
  runId: string,
): ReviewQcTarget[] {
  return findings.map((finding) => ({
    findingId: finding.findingId,
    rowId: finding.rowId,

    runId,
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
 * Маппинг ReviewFinding -> backend ReviewFindingKey.
 */
function toReviewFindingKey(
  finding: ReviewFinding,
  runId: string,
): ReviewFindingKey {
  return {
    run_id: runId,
    document_id: finding.documentId,
    check_id: finding.checkId,
    segment_id: finding.segmentId ?? null,
  };
}

/**
 * Дедупликация одинаковых ReviewFindingKey, чтобы не слать backend
 * избыточные записи, если несколько findings ссылаются на одну ячейку.
 */
function dedupeFindingKeys(keys: ReviewFindingKey[]): ReviewFindingKey[] {
  const seen = new Set<string>();
  const out: ReviewFindingKey[] = [];

  for (const key of keys) {
    const dedupKey = [
      key.run_id,
      key.document_id,
      key.check_id,
      key.segment_id ?? "",
    ].join("|");

    if (seen.has(dedupKey)) continue;
    seen.add(dedupKey);
    out.push(key);
  }

  return out;
}

/**
 * Проверяет, можно ли текущую review selection отправить в QC.
 */
export function getReviewQcCapability(
  selection: ReviewSelectionItem[],
  selectedFindings: ReviewFinding[],
  runId: string | null | undefined,
): ReviewQcCapability {
  if (!selection.length) {
    return {
      supported: false,
      reason: "empty_selection",
      message: null,
      selectedRowsCount: 0,
      selectedFindingsCount: 0,
    };
  }

  if (!selectedFindings.length) {
    return {
      supported: false,
      reason: "no_findings_in_selection",
      message:
        "В выбранных строках нет findings, к которым можно применить QC-действие.",
      selectedRowsCount: selection.length,
      selectedFindingsCount: 0,
    };
  }

  if (!runId) {
    return {
      supported: false,
      reason: "mixed_run_ids",
      message: "Не определён run для QC-действия.",
      selectedRowsCount: selection.length,
      selectedFindingsCount: selectedFindings.length,
    };
  }

  return {
    supported: true,
    reason: null,
    message: null,
    selectedRowsCount: selection.length,
    selectedFindingsCount: selectedFindings.length,
  };
}

/**
 * Сообщение-плейсхолдер для UI, когда QC недоступен.
 * Возвращает null, если действие доступно или selection пуст.
 *
 * Для пустой selection UI должен показывать собственный empty-state,
 * а не дублировать его как ноту.
 */
export function getReviewQcDisabledNote(
  capability: ReviewQcCapability,
): string | null {
  if (capability.supported) return null;
  if (capability.reason === "empty_selection") return null;
  return capability.message;
}

/**
 * Собирает payload для POST /api/v1/qc/review/bulk.
 *
 * Возвращает null, если payload собрать невозможно
 * (например, нет findings или не задан runId).
 */
export function buildReviewQcBulkPayload(
  findings: ReviewFinding[],
  runId: string | null | undefined,
  qcStatus: ReviewQcStatus,
  comment?: string | null,
): ReviewQCBulkUpdateRequest | null {
  if (!runId || !findings.length) return null;

  const keys = dedupeFindingKeys(
    findings.map((finding) => toReviewFindingKey(finding, runId)),
  );

  if (!keys.length) return null;

  const normalizedComment =
    typeof comment === "string" && comment.trim().length > 0
      ? comment.trim()
      : null;

  return {
    findings: keys,
    qc_status: qcStatus,
    comment: normalizedComment,
  };
}


