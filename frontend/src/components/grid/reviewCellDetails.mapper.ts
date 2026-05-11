// =============================================================
// src/components/grid/reviewCellDetails.mapper.ts
// Shared helpers for transforming review cell data into:
// - details drawer payload
// - matrix/list grid display strings
// - tooltip / summary / export-friendly text
// =============================================================

import type { SeverityLevel } from "../../types";
import type { MatrixCellDTO } from "../../types/dealReview";
import type {
  ReviewGridRow,
  ReviewCheckColumn,
} from "../../pages/tabs/grid/reviewGrid.types";
import type { MatrixCellDetailsCell } from "./DDMatrixCellDetails";

type ExtractedFieldDTO = MatrixCellDTO["extracted"] extends Array<infer T>
  ? T
  : never;

function normalizeString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function normalizeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizeBooleanRecord(
  value: unknown,
): Record<string, boolean> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const entries = Object.entries(value).filter(
    ([key, flag]) => typeof key === "string" && typeof flag === "boolean",
  );

  if (!entries.length) {
    return null;
  }

  const result: Record<string, boolean> = {};
  for (const [key, flag] of entries) {
    result[key] = flag;
  }
  return result;
}

/**
 * Type guard for supported risk severities.
 */
export function isRiskSeverity(
  value: string | null | undefined,
): value is SeverityLevel {
  return value === "critical" || value === "high" || value === "medium";
}

/**
 * Признак того, что юрист уже принял решение по этому finding.
 * pending / null означают, что review ещё не проводился.
 *
 * Используется в getCellStatusText для перекрытия machine-generated текста
 * единым "Просмотрено юристом" — детализация решения доступна в отдельной
 * колонке "QC" и в drawer.
 */
function isQcReviewed(cell: MatrixCellDTO): boolean {
  return (
    cell.qc_status === "approved" ||
    cell.qc_status === "rejected" ||
    cell.qc_status === "needs_review"
  );
}

/**
 * Human-readable status for matrix/list presentation.
 *
 * Приоритет: QC review status перекрывает machine-generated результат.
 * Если юрист уже посмотрел finding (qc_status != pending/null), показываем
 * единый маркер "Просмотрено юристом". Конкретное решение (approved /
 * rejected / needs_review) видно в отдельной колонке "QC" и в drawer.
 *
 * Это соответствует legal review workflow:
 * - "Требует внимания юриста" — нужно посмотреть
 * - "Просмотрено юристом" — посмотрено, детали в QC
 */
export function getCellStatusText(cell: MatrixCellDTO): string {
  if (isQcReviewed(cell)) {
    return "Просмотрено юристом";
  }

  if (cell.result === "fail") {
    if (cell.severity === "critical" || cell.severity === "high") {
      return "Требует внимания юриста";
    }
    return "Идентифицирован";
  }

  if (cell.result === "unclear") {
    return "Требует внимания юриста";
  }

  return "Не найден";
}

/**
 * Safe severity extraction.
 */
export function getCellSeverity(cell: MatrixCellDTO): SeverityLevel | null {
  return isRiskSeverity(cell.severity) ? cell.severity : null;
}

/**
 * Stable result key for filters / badges / list grouping.
 */
export function getCellResultKey(
  cell: MatrixCellDTO | null | undefined,
): string {
  if (!cell) return "missing";
  return normalizeString(cell.result) || "unknown";
}

/**
 * Page / clause location label.
 * Example: "стр. 5 · clause_123"
 */
export function getCellLocationText(cell: MatrixCellDTO): string {
  const pageText = cell.page != null ? `стр. ${cell.page}` : "";
  const clauseText = normalizeString(cell.clause_uid) || "";

  if (pageText && clauseText) return `${pageText} · ${clauseText}`;
  return pageText || clauseText || "";
}

/**
 * Segment / chunk label.
 * Example: "Schedule A · Chunk #2"
 */
export function getCellSegmentText(cell: MatrixCellDTO): string {
  const segmentText =
    normalizeString(cell.segment_title) ||
    normalizeString(cell.segment_id) ||
    "";
  const chunkText =
    cell.chunk_index != null ? `Chunk #${cell.chunk_index}` : "";

  if (segmentText && chunkText) return `${segmentText} · ${chunkText}`;
  return segmentText || chunkText || "";
}

/**
 * Created-at extraction from optional backend field.
 */
export function getCellCreatedAt(cell: MatrixCellDTO): string | null {
  const candidate = (cell as { created_at?: unknown }).created_at;
  return normalizeString(candidate);
}

/**
 * QC comment extraction from optional backend field.
 */
export function getCellQcComment(cell: MatrixCellDTO): string | null {
  const candidate = (cell as { qc_comment?: unknown }).qc_comment;
  return normalizeString(candidate);
}

/**
 * Quality flags extraction from optional backend field.
 */
export function getCellQualityFlags(
  cell: MatrixCellDTO,
): Record<string, boolean> | null {
  const candidate = (cell as { quality_flags?: unknown }).quality_flags;
  return normalizeBooleanRecord(candidate);
}

/**
 * Compact summary for list cells / quick overviews.
 * Keeps snippet out to avoid noisy grid/export strings.
 */
export function getCellSummaryText(
  cell: MatrixCellDTO | null | undefined,
): string {
  if (!cell) return "—";

  return [
    getCellStatusText(cell),
    getCellSeverity(cell),
    getCellLocationText(cell),
    getCellSegmentText(cell),
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * Tooltip text for matrix/list grid.
 * Snippet is preferred here because tooltip is a rich hover surface.
 */
export function buildCellTooltip(
  cell: MatrixCellDTO | null | undefined,
): string {
  if (!cell) return "";

  return (
    normalizeString(cell.snippet) ||
    getCellLocationText(cell) ||
    getCellSegmentText(cell) ||
    getCellStatusText(cell)
  );
}

/**
 * Export / clipboard friendly formatter for AG Grid valueFormatter.
 * Keep it concise because AG Grid uses valueFormatter for export by default.
 */
export function formatRiskCellValue(
  cell: MatrixCellDTO | null | undefined,
): string {
  if (!cell) return "";

  const severity = getCellSeverity(cell);
  const severityText = severity ? ` [${severity}]` : "";
  const location = getCellLocationText(cell);
  const segment = getCellSegmentText(cell);

  return [
    getCellStatusText(cell) + severityText,
    location || null,
    segment || null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * Internal mapper for extracted field payload.
 */
function mapExtractedField(
  field: ExtractedFieldDTO,
): MatrixCellDetailsCell["extractedFields"][number] {
  return {
    fieldName: normalizeString(field.field_name) || "—",
    fieldValue: normalizeString(field.field_value) || "—",
    fieldFormat: normalizeString(field.field_format),
    fieldSource: normalizeString(
      (field as { field_source?: unknown }).field_source,
    ),
    page: normalizeNumber((field as { page?: unknown }).page),
    clauseUid: normalizeString(
      (field as { clause_uid?: unknown }).clause_uid,
    ),
    segmentId: normalizeString(
      (field as { segment_id?: unknown }).segment_id,
    ),
    chunkId: normalizeString((field as { chunk_id?: unknown }).chunk_id),
    chunkIndex: normalizeNumber(
      (field as { chunk_index?: unknown }).chunk_index,
    ),
  };
}

/**
 * Main shared mapper:
 * review row + review column + raw matrix cell -> details drawer payload
 */
export function mapReviewCellToDetailsCell(
  row: ReviewGridRow,
  meta: ReviewCheckColumn,
  cell: MatrixCellDTO,
): MatrixCellDetailsCell {
  return {
    result: normalizeString(cell.result) || "unknown",
    severity: getCellSeverity(cell),
    snippet: normalizeString(cell.snippet),
    page: normalizeNumber(cell.page),
    clauseUid: normalizeString(cell.clause_uid),
    confidence: normalizeNumber(cell.confidence),
    qcStatus: cell.qc_status ?? null,
    conditionalTriggered: Boolean(cell.conditional_check_triggered),
    triggerName: normalizeString(cell.trigger_name),

    origin: normalizeString(meta.origin),
    createdAt: getCellCreatedAt(cell),
    qcComment: getCellQcComment(cell),
    qualityFlags: getCellQualityFlags(cell),

    docType: normalizeString(row.docType),
    docClassificationLevel: normalizeString(row.classificationLevel),
    docClassificationConfidence: normalizeNumber(row.classificationConfidence),

    segmentId:
      normalizeString(cell.segment_id) || normalizeString(row.segmentId),
    segmentTitle:
      normalizeString(cell.segment_title) || normalizeString(row.segmentTitle),
    segmentType:
      normalizeString(cell.segment_type) || normalizeString(row.segmentType),
    segmentOrder:
      normalizeNumber(cell.segment_order) ?? normalizeNumber(row.segmentOrder),
    isPrimarySegment:
      typeof cell.is_primary_segment === "boolean"
        ? cell.is_primary_segment
        : typeof row.isPrimarySegment === "boolean"
          ? row.isPrimarySegment
          : null,
    chunkId: normalizeString(cell.chunk_id),
    chunkIndex: normalizeNumber(cell.chunk_index),

    extractedFields: Array.isArray(cell.extracted)
      ? cell.extracted.map(mapExtractedField)
      : [],
  };
}


