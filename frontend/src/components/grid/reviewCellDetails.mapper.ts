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

/**
 * Type guard for supported risk severities.
 */
export function isRiskSeverity(
  value: string | null | undefined,
): value is SeverityLevel {
  return value === "critical" || value === "high" || value === "medium";
}

/**
 * Human-readable status for matrix/list presentation.
 */
export function getCellStatusText(cell: MatrixCellDTO): string {
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
  return cell.result || "unknown";
}

/**
 * Page / clause location label.
 * Example: "стр. 5 · clause_123"
 */
export function getCellLocationText(cell: MatrixCellDTO): string {
  const pageText = cell.page != null ? `стр. ${cell.page}` : "";
  const clauseText = cell.clause_uid ? cell.clause_uid : "";

  if (pageText && clauseText) return `${pageText} · ${clauseText}`;
  return pageText || clauseText || "";
}

/**
 * Segment / chunk label.
 * Example: "Schedule A · Chunk #2"
 */
export function getCellSegmentText(cell: MatrixCellDTO): string {
  const segmentText = cell.segment_title || cell.segment_id || "";
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
  return typeof candidate === "string" ? candidate : null;
}

/**
 * QC comment extraction from optional backend field.
 */
export function getCellQcComment(cell: MatrixCellDTO): string | null {
  const candidate = (cell as { qc_comment?: unknown }).qc_comment;
  return typeof candidate === "string" ? candidate : null;
}

/**
 * Quality flags extraction from optional backend field.
 */
export function getCellQualityFlags(
  cell: MatrixCellDTO,
): Record<string, boolean> | null {
  const candidate = (cell as { quality_flags?: unknown }).quality_flags;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return null;
  }

  return Object.fromEntries(
    Object.entries(candidate).filter(
      ([, value]) => typeof value === "boolean",
    ),
  ) as Record<string, boolean>;
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
    cell.snippet?.trim() ||
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
    fieldName: field.field_name,
    fieldValue: field.field_value,
    fieldFormat: field.field_format ?? null,
    fieldSource:
      typeof (field as { field_source?: unknown }).field_source === "string"
        ? ((field as { field_source?: string }).field_source ?? null)
        : null,
    page:
      typeof (field as { page?: unknown }).page === "number"
        ? ((field as { page?: number }).page ?? null)
        : null,
    clauseUid:
      typeof (field as { clause_uid?: unknown }).clause_uid === "string"
        ? ((field as { clause_uid?: string }).clause_uid ?? null)
        : null,
    segmentId:
      typeof (field as { segment_id?: unknown }).segment_id === "string"
        ? ((field as { segment_id?: string }).segment_id ?? null)
        : null,
    chunkId:
      typeof (field as { chunk_id?: unknown }).chunk_id === "string"
        ? ((field as { chunk_id?: string }).chunk_id ?? null)
        : null,
    chunkIndex:
      typeof (field as { chunk_index?: unknown }).chunk_index === "number"
        ? ((field as { chunk_index?: number }).chunk_index ?? null)
        : null,
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
    result: cell.result,
    severity: getCellSeverity(cell),
    snippet: cell.snippet ?? null,
    page: cell.page ?? null,
    clauseUid: cell.clause_uid ?? null,
    confidence: cell.confidence ?? null,
    qcStatus: cell.qc_status ?? null,
    conditionalTriggered: !!cell.conditional_check_triggered,
    triggerName: cell.trigger_name ?? null,

    origin: meta.origin ?? null,
    createdAt: getCellCreatedAt(cell),
    qcComment: getCellQcComment(cell),
    qualityFlags: getCellQualityFlags(cell),

    docType: row.docType ?? null,
    docClassificationLevel: row.classificationLevel ?? null,
    docClassificationConfidence: row.classificationConfidence ?? null,

    segmentId: cell.segment_id ?? row.segmentId ?? null,
    segmentTitle: cell.segment_title ?? row.segmentTitle ?? null,
    segmentType: cell.segment_type ?? row.segmentType ?? null,
    segmentOrder: cell.segment_order ?? row.segmentOrder ?? null,
    isPrimarySegment: cell.is_primary_segment ?? row.isPrimarySegment ?? null,
    chunkId: cell.chunk_id ?? null,
    chunkIndex: cell.chunk_index ?? null,

    extractedFields: Array.isArray(cell.extracted)
      ? cell.extracted.map(mapExtractedField)
      : [],
  };
}


