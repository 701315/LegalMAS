// =============================================================
// src/pages/tabs/grid/reviewGrid.selectors.ts
// Селекторы для преобразования DDMatrixResponseDTO в review domain модель.
//
// Для непрофессионального программиста:
// Этот файл берёт ответ backend dd-matrix API и превращает его
// в удобную форму для review grid на фронтенде.
//
// ВАЖНО:
// - единственный source of truth для review rows/findings — dto.segment_documents;
// - legacy fallback через dto.documents удалён;
// - если backend не прислал segment_documents, UI просто получит пустую модель,
//   а не попытается "угадать" строки из другого формата.
// =============================================================

import type {
  DDMatrixResponseDTO,
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

const ROOT_SEGMENT_KEY = "__root__";

/**
 * Главный селектор: берёт сырой DTO и возвращает полную derived модель.
 *
 * Для непрофессионального программиста:
 * Если backend ещё не успел прислать данные или прислал некорректный объект,
 * мы возвращаем безопасное пустое состояние для UI.
 */
export function selectReviewGridData(
  dto: DDMatrixResponseDTO | null | undefined,
): ReviewGridDerivedData {
  if (
    !dto ||
    !Array.isArray(dto.checks) ||
    !Array.isArray(dto.segment_documents)
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

    // Для непрофессионального программиста:
    // Если у строки есть segment_id, значит это часть multi-document файла.
    // Полные composition-метаданные backend пока не присылает в этом DTO,
    // поэтому здесь держим только аккуратный минимальный признак.
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
 * Строит строки review matrix.
 *
 * Для непрофессионального программиста:
 * Одна строка review grid = один logical document / segment row
 * из dto.segment_documents.
 */
function selectRows(dto: DDMatrixResponseDTO): ReviewGridRow[] {
  return (dto.segment_documents ?? []).map(mapSegmentRowToReviewRow);
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

    // Canonical display semantics — thin projection из MatrixCellDTO.
    // Selector не интерпретирует, только проецирует.
    displayText: cell.display_text ?? null,
    reviewStatus: cell.review_status ?? null,
    reviewMessage: cell.review_message ?? null,
    needsManualReview: cell.needs_manual_review ?? false,
    uiMode: cell.ui_mode ?? null,

    cell,
  };
}

/**
 * Разворачивает segment-based матрицу в плоский список findings.
 *
 * Для непрофессионального программиста:
 * Внутри одной строки матрицы может быть несколько проверок.
 * Эта функция делает из таких строк обычный плоский список записей,
 * который удобно фильтровать, экспортировать и считать.
 */
function selectFindings(dto: DDMatrixResponseDTO): ReviewFinding[] {
  const findings: ReviewFinding[] = [];

  for (const row of dto.segment_documents ?? []) {
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



