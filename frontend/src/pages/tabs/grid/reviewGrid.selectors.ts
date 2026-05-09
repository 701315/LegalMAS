// =============================================================
// src/pages/tabs/grid/reviewGrid.selectors.ts
// Селекторы для преобразования DDMatrixResponseDTO в review domain модель.
// Primary source of truth for grid rows/findings: dto.segment_documents.
// Legacy fallback через dto.documents оставлен временно внутри этого модуля.
// =============================================================

import type {
  DDMatrixResponseDTO,
  DocumentMatrixRowDTO,
  MatrixCellDTO,
  SegmentMatrixRowDTO,
} from "../../../types/dealReview";
import type {
  ReviewGridRow,
  ReviewFinding,
  ReviewGridStats,
  ReviewCheckColumn,
  ReviewGridDerivedData,
} from "./reviewGrid.types";

interface SegmentBucket {
  segmentKey: string;
  segmentId: string | null;
  segmentTitle: string | null;
  segmentType: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;
  cellsByCheckId: Record<string, MatrixCellDTO | undefined>;
}

const ROOT_SEGMENT_KEY = "__root__";

/**
 * Главный селектор: берёт сырой DTO и возвращает полную derived модель.
 */
export function selectReviewGridData(
  dto: DDMatrixResponseDTO | null | undefined,
): ReviewGridDerivedData {
  if (
    !dto ||
    !Array.isArray(dto.checks) ||
    (!Array.isArray(dto.segment_documents) && !Array.isArray(dto.documents))
  ) {
    return {
      columns: [],
      rows: [],
      findings: [],
      stats: {
        documentsCount: 0,
        rowsCount: 0,
        findingsCount: 0,
        checksCount: 0,
        criticalCount: 0,
        highCount: 0,
        mediumCount: 0,
        unclearCount: 0,
        noQcCount: 0,
      },
      availableDocTypes: [],
      availableOrigins: [],
    };
  }

  const columns = selectColumns(dto);
  const rows = selectRows(dto);
  const findings = selectFindings(dto);
  const stats = selectStats(rows, findings);
  const availableDocTypes = selectAvailableDocTypes(rows);
  const availableOrigins = selectAvailableOrigins(columns);

  return {
    columns,
    rows,
    findings,
    stats,
    availableDocTypes,
    availableOrigins,
  };
}

/**
 * Извлекает метаданные проверок из DTO.
 */
function selectColumns(dto: DDMatrixResponseDTO): ReviewCheckColumn[] {
  return dto.checks
    .slice()
    .sort((a, b) => a.order_index - b.order_index)
    .map((check) => ({
      checkId: check.check_id,
      checkName: check.check_name || check.check_id,
      origin: check.origin ?? null,
      severity: check.severity ?? null,
    }));
}

function buildRowId(documentId: string, segmentKey: string): string {
  return `segment:${documentId}:${segmentKey}`;
}

function getCellSegmentKey(cell: MatrixCellDTO | undefined): string {
  if (!cell) return ROOT_SEGMENT_KEY;
  return cell.segment_id ?? ROOT_SEGMENT_KEY;
}

function getSegmentRowKey(row: SegmentMatrixRowDTO): string {
  return row.segment_id ?? ROOT_SEGMENT_KEY;
}

function buildCellsByCheckId(
  results: Record<string, MatrixCellDTO> | null | undefined,
): Record<string, MatrixCellDTO | undefined> {
  return Object.fromEntries(
    Object.entries(results ?? {}).map(([checkId, cell]) => [checkId, cell]),
  );
}

function countCellSeverities(cells: Array<MatrixCellDTO | undefined>) {
  return {
    totalCritical: cells.filter((c) => c?.severity === "critical").length,
    totalHigh: cells.filter((c) => c?.severity === "high").length,
    totalMedium: cells.filter((c) => c?.severity === "medium").length,
    totalUnclear: cells.filter((c) => c?.result === "unclear").length,
  };
}

function mapSegmentRowToReviewRow(row: SegmentMatrixRowDTO): ReviewGridRow {
  const cellsByCheckId = buildCellsByCheckId(row.results);
  const counts = countCellSeverities(Object.values(cellsByCheckId));
  const segmentKey = getSegmentRowKey(row);

  return {
    rowId: buildRowId(row.document_id, segmentKey),

    documentId: row.document_id,
    documentName: row.document_name || "[no name]",
    docType: row.doc_type ?? null,
    folderPath: row.folder_path ?? null,

    segmentId: row.segment_id ?? null,
    segmentTitle: row.segment_title ?? null,
    segmentType: row.segment_type ?? null,
    segmentOrder: row.segment_order ?? null,
    isPrimarySegment: row.is_primary_segment ?? null,

    classificationLevel: row.classification_level ?? null,
    classificationConfidence: row.classification_confidence ?? null,
    requiresManualReview: row.requires_manual_review ?? false,

    // Segment row DTO не несёт composition metadata напрямую.
    isMultiDocument: row.segment_id != null,
    segmentCount: undefined,
    primarySegmentLabel: row.is_primary_segment
      ? (row.segment_title ?? row.segment_type ?? row.segment_id ?? null)
      : null,

    totalCritical: counts.totalCritical,
    totalHigh: counts.totalHigh,
    totalMedium: counts.totalMedium,
    totalUnclear: counts.totalUnclear,

    cellsByCheckId,
  };
}

/**
 * Temporary fallback path: reconstruct segment rows from dto.documents.
 * Оставлено только пока backend/source contract может приходить без segment_documents.
 * Удалить после полного перехода на review-only stable contract.
 */
function getSegmentBuckets(
  doc: DocumentMatrixRowDTO,
): Map<string, SegmentBucket> {
  const buckets = new Map<string, SegmentBucket>();
  const results = doc.results ?? {};

  for (const [checkId, cell] of Object.entries(results)) {
    const segmentKey = getCellSegmentKey(cell);
    const existing = buckets.get(segmentKey);

    if (existing) {
      existing.cellsByCheckId[checkId] = cell;
      continue;
    }

    buckets.set(segmentKey, {
      segmentKey,
      segmentId: cell.segment_id ?? null,
      segmentTitle: cell.segment_title ?? null,
      segmentType: cell.segment_type ?? null,
      segmentOrder: cell.segment_order ?? null,
      isPrimarySegment: cell.is_primary_segment ?? null,
      cellsByCheckId: {
        [checkId]: cell,
      },
    });
  }

  if (buckets.size === 0) {
    buckets.set(ROOT_SEGMENT_KEY, {
      segmentKey: ROOT_SEGMENT_KEY,
      segmentId: null,
      segmentTitle: null,
      segmentType: null,
      segmentOrder: null,
      isPrimarySegment: null,
      cellsByCheckId: {},
    });
  }

  return buckets;
}

function compareSegmentBuckets(a: SegmentBucket, b: SegmentBucket): number {
  const orderA = a.segmentOrder ?? Number.MAX_SAFE_INTEGER;
  const orderB = b.segmentOrder ?? Number.MAX_SAFE_INTEGER;

  if (orderA !== orderB) {
    return orderA - orderB;
  }

  const primaryA = a.isPrimarySegment ? 0 : 1;
  const primaryB = b.isPrimarySegment ? 0 : 1;

  if (primaryA !== primaryB) {
    return primaryA - primaryB;
  }

  const titleA = a.segmentTitle ?? a.segmentId ?? a.segmentKey;
  const titleB = b.segmentTitle ?? b.segmentId ?? b.segmentKey;

  return titleA.localeCompare(titleB);
}

function selectRowsFromDocumentsFallback(
  dto: DDMatrixResponseDTO,
): ReviewGridRow[] {
  return dto.documents.flatMap((doc) => {
    const buckets = Array.from(getSegmentBuckets(doc).values()).sort(
      compareSegmentBuckets,
    );

    return buckets.map((bucket) => {
      const cells = Object.values(bucket.cellsByCheckId);
      const counts = countCellSeverities(cells);

      return {
        rowId: buildRowId(doc.document_id, bucket.segmentKey),

        documentId: doc.document_id,
        documentName: doc.document_name || "[no name]",
        docType: doc.doc_type ?? null,
        folderPath: doc.folder_path ?? null,

        segmentId: bucket.segmentId,
        segmentTitle: bucket.segmentTitle,
        segmentType: bucket.segmentType,
        segmentOrder: bucket.segmentOrder,
        isPrimarySegment: bucket.isPrimarySegment,

        classificationLevel: doc.classification_level ?? null,
        classificationConfidence: doc.classification_confidence ?? null,
        requiresManualReview: doc.requires_manual_review ?? false,

        isMultiDocument: doc.results
          ? Object.values(doc.results).some((cell) => !!cell?.segment_id)
          : false,
        segmentCount: buckets.length,
        primarySegmentLabel: buckets.find((b) => b.isPrimarySegment)?.segmentTitle ?? null,

        totalCritical: counts.totalCritical,
        totalHigh: counts.totalHigh,
        totalMedium: counts.totalMedium,
        totalUnclear: counts.totalUnclear,

        cellsByCheckId: bucket.cellsByCheckId,
      };
    });
  });
}

/**
 * Строит строки review matrix.
 *
 * Primary row model:
 * - одна строка = один logical segment row из dto.segment_documents.
 * Fallback:
 * - если segment_documents пуст, временно восстанавливаем строки из dto.documents.
 */
function selectRows(dto: DDMatrixResponseDTO): ReviewGridRow[] {
  if (dto.segment_documents && dto.segment_documents.length > 0) {
    return dto.segment_documents.map(mapSegmentRowToReviewRow);
  }

  return selectRowsFromDocumentsFallback(dto);
}

function mapSegmentRowFinding(
  row: SegmentMatrixRowDTO,
  checkId: string,
  checkName: string,
  origin: string | null,
  checkSeverityBaseline: string | null,
  cell: MatrixCellDTO,
): ReviewFinding {
  const segmentKey = getSegmentRowKey(row);
  const rowId = buildRowId(row.document_id, segmentKey);
  const findingId = `${row.document_id}__${checkId}__${segmentKey}__${cell.chunk_id ?? "none"}`;

  return {
    findingId,
    rowId,

    documentId: row.document_id,
    documentName: row.document_name || "[no name]",
    docType: row.doc_type ?? null,
    folderPath: row.folder_path ?? null,

    segmentId: row.segment_id ?? cell.segment_id ?? null,
    segmentTitle: row.segment_title ?? cell.segment_title ?? null,
    segmentType: row.segment_type ?? cell.segment_type ?? null,
    segmentOrder: row.segment_order ?? cell.segment_order ?? null,
    isPrimarySegment: row.is_primary_segment ?? cell.is_primary_segment ?? null,

    checkId,
    checkName,
    origin,
    checkSeverityBaseline,

    result: cell.result,
    severity: cell.severity ?? null,
    qcStatus: cell.qc_status ?? null,
    confidence: cell.confidence ?? null,

    snippet: cell.snippet ?? null,
    page: cell.page ?? null,
    clauseUid: cell.clause_uid ?? null,

    conditionalTriggered: cell.conditional_check_triggered ?? false,
    triggerName: cell.trigger_name ?? null,

    chunkId: cell.chunk_id ?? null,
    chunkIndex: cell.chunk_index ?? null,

    cell,
  };
}

function selectFindingsFromSegmentDocuments(
  dto: DDMatrixResponseDTO,
): ReviewFinding[] {
  if (!dto.segment_documents) return [];

  const findings: ReviewFinding[] = [];

  for (const row of dto.segment_documents) {
    const results = row.results ?? {};

    for (const check of dto.checks) {
      const cell = results[check.check_id];
      if (!cell) continue;

      findings.push(
        mapSegmentRowFinding(
          row,
          check.check_id,
          check.check_name || check.check_id,
          check.origin ?? null,
          check.severity ?? null,
          cell,
        ),
      );
    }
  }

  return findings;
}

/**
 * Temporary fallback path from dto.documents.
 */
function selectFindingsFromDocumentsFallback(
  dto: DDMatrixResponseDTO,
): ReviewFinding[] {
  const findings: ReviewFinding[] = [];

  for (const doc of dto.documents) {
    const results = doc.results ?? {};

    for (const check of dto.checks) {
      const cell = results[check.check_id];
      if (!cell) continue;

      const segmentKey = getCellSegmentKey(cell);
      const rowId = buildRowId(doc.document_id, segmentKey);
      const findingId = `${doc.document_id}__${check.check_id}__${segmentKey}__${cell.chunk_id ?? "none"}`;

      findings.push({
        findingId,
        rowId,

        documentId: doc.document_id,
        documentName: doc.document_name || "[no name]",
        docType: doc.doc_type ?? null,
        folderPath: doc.folder_path ?? null,

        segmentId: cell.segment_id ?? null,
        segmentTitle: cell.segment_title ?? null,
        segmentType: cell.segment_type ?? null,
        segmentOrder: cell.segment_order ?? null,
        isPrimarySegment: cell.is_primary_segment ?? null,

        checkId: check.check_id,
        checkName: check.check_name || check.check_id,
        origin: check.origin ?? null,
        checkSeverityBaseline: check.severity ?? null,

        result: cell.result,
        severity: cell.severity ?? null,
        qcStatus: cell.qc_status ?? null,
        confidence: cell.confidence ?? null,

        snippet: cell.snippet ?? null,
        page: cell.page ?? null,
        clauseUid: cell.clause_uid ?? null,

        conditionalTriggered: cell.conditional_check_triggered ?? false,
        triggerName: cell.trigger_name ?? null,

        chunkId: cell.chunk_id ?? null,
        chunkIndex: cell.chunk_index ?? null,

        cell,
      });
    }
  }

  return findings;
}

/**
 * Разворачивает матрицу в плоский список findings.
 *
 * Primary source:
 * - dto.segment_documents
 * Fallback:
 * - dto.documents
 */
function selectFindings(dto: DDMatrixResponseDTO): ReviewFinding[] {
  if (dto.segment_documents && dto.segment_documents.length > 0) {
    return selectFindingsFromSegmentDocuments(dto);
  }

  return selectFindingsFromDocumentsFallback(dto);
}


/**
 * Вычисляет статистику по строкам и findings.
 */
function selectStats(
  rows: ReviewGridRow[],
  findings: ReviewFinding[],
): ReviewGridStats {
  const uniqueDocumentIds = new Set(rows.map((r) => r.documentId));
  const uniqueCheckIds = new Set(findings.map((f) => f.checkId));

  const criticalCount = findings.filter((f) => f.severity === "critical").length;
  const highCount = findings.filter((f) => f.severity === "high").length;
  const mediumCount = findings.filter((f) => f.severity === "medium").length;
  const unclearCount = findings.filter((f) => f.result === "unclear").length;
  const noQcCount = findings.filter(
    (f) => !f.qcStatus || f.qcStatus === "pending",
  ).length;

  return {
    documentsCount: uniqueDocumentIds.size,
    rowsCount: rows.length,
    findingsCount: findings.length,
    checksCount: uniqueCheckIds.size,
    criticalCount,
    highCount,
    mediumCount,
    unclearCount,
    noQcCount,
  };
}

/**
 * Собирает уникальные типы документов для фильтра.
 */
function selectAvailableDocTypes(rows: ReviewGridRow[]): string[] {
  const types = new Set<string>();

  for (const row of rows) {
    if (row.docType) {
      types.add(row.docType);
    }
  }

  return Array.from(types).sort();
}

/**
 * Собирает уникальные origins проверок для фильтра.
 */
function selectAvailableOrigins(columns: ReviewCheckColumn[]): string[] {
  const origins = new Set<string>();

  for (const column of columns) {
    if (column.origin) {
      origins.add(column.origin);
    }
  }

  return Array.from(origins).sort();
}

