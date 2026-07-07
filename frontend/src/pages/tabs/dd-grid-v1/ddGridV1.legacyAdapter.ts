// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.legacyAdapter.ts
// Адаптер V1-модели → legacy review model (rows / findings / columns / stats).
//
// Зачем:
// - QC bulk actions, Export, Filters на фронте написаны поверх
//   ReviewGridRow / ReviewFinding / ReviewCheckColumn / ReviewGridStats;
// - переписывать их для V1 нецелесообразно (production surface);
// - вместо этого адаптер строит те же самые структуры из V1 dataset
//   и позволяет переиспользовать всю существующую logic без правок.
//
// Правила:
// - никаких хардкодов конкретных check_id / column_id / doc_type;
// - не выдумываем поля, которых V1 контракт не даёт (severity, qc_status,
//   confidence, segments и т.п.) — используем безопасные дефолты;
// - идентификаторы rowId/findingId строятся детерминированно и
//   не пересекаются с legacy segment: id-пространством.
// =============================================================

import type {
  MatrixCellDTO,
  ReviewCheckOrigin,
} from "../../../types/dealReview";

import type {
  ReviewCheckColumn,
  ReviewFinding,
  ReviewGridDerivedData,
  ReviewGridRow,
  ReviewGridStats,
} from "../grid/reviewGrid.types";

import type {
  DDGridV1DerivedModel,
  DDGridV1MatrixRow,
} from "./ddGridV1.types";
import type {
  DDGridV1CellValueDTO,
  DDGridV1DrawerContentDTO,
  DDGridV1DrawerFieldDTO,
} from "../../../types/dealReview";
import { resolveDDGridV1DrawerReason } from "./ddGridV1.drawer";

// -------------------------------------------------------------
// Id builders (universal, deterministic)
// -------------------------------------------------------------

/**
 * Row id для legacy-совместимого selection.
 * Не пересекается с legacy segment: id-пространством.
 */
function buildLegacyRowId(documentId: string): string {
  return `docv1:${documentId}`;
}

/**
 * Finding id для legacy-совместимого selection / QC dedupe.
 * Один finding = одна пара (документ × check).
 */
function buildLegacyFindingId(documentId: string, checkId: string): string {
  return `docv1:${documentId}__${checkId}`;
}

// -------------------------------------------------------------
// Origin resolution (universal — по scope, без хардкодов)
// -------------------------------------------------------------

/**
 * Возвращает ReviewCheckOrigin по scope check-а.
 *
 * Использует уже существующий legacy union, чтобы фильтры и label-map
 * ReviewGridFilters (ORIGIN_LABELS) продолжали работать без правок.
 */
function resolveOriginFromScope(scope: "global" | "docType"): ReviewCheckOrigin {
  return scope === "global" ? "GLOBAL_PLAYBOOK" : "DOCUMENT_TYPE";
}

// -------------------------------------------------------------
// Column dedup by check_id (universal)
// -------------------------------------------------------------

/**
 * V1 иерархия может содержать один и тот же check_id в разных ветках
 * (например, global + doc_type). Для legacy ReviewCheckColumn нам нужен
 * плоский список уникальных check-ов.
 *
 * Стратегия дедупа:
 * - ключ уникальности — checkId;
 * - если check встречается в global и в docType — origin = "GLOBAL_PLAYBOOK"
 *   (глобальные check-и по семантике доминируют).
 */
interface CheckSummary {
  checkId: string;
  checkName: string;
  origin: ReviewCheckOrigin;
}

function collectUniqueChecks(model: DDGridV1DerivedModel): CheckSummary[] {
  const byCheckId = new Map<string, CheckSummary>();

  const upsert = (
    checkId: string,
    checkName: string,
    scope: "global" | "docType",
  ) => {
    const existing = byCheckId.get(checkId);
    if (!existing) {
      byCheckId.set(checkId, {
        checkId,
        checkName,
        origin: resolveOriginFromScope(scope),
      });
      return;
    }
    // Если уже есть и текущий scope глобальный — повышаем origin до GLOBAL_PLAYBOOK.
    if (scope === "global" && existing.origin !== "GLOBAL_PLAYBOOK") {
      byCheckId.set(checkId, { ...existing, origin: "GLOBAL_PLAYBOOK" });
    }
  };

  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      upsert(check.checkId, check.checkName, "global");
    }
  }
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        upsert(check.checkId, check.checkName, "docType");
      }
    }
  }

  return Array.from(byCheckId.values());
}

// -------------------------------------------------------------
// Location extraction from drawer.fields (universal)
// -------------------------------------------------------------

interface LocationHints {
  page: number | null;
  clauseUid: string | null;
}

/**
 * Возвращает первую доступную (page, clause_ref) пару из drawer.fields.
 * Не различает exact/approximate — это делает UI-слой отдельно через
 * classifyDDGridV1LocationAvailability.
 */
function extractFirstLocation(
  fields: DDGridV1DrawerFieldDTO[] | undefined,
): LocationHints {
  if (!fields || fields.length === 0) {
    return { page: null, clauseUid: null };
  }
  let page: number | null = null;
  let clauseUid: string | null = null;

  for (const f of fields) {
    if (page === null && typeof f.location_page === "number") {
      page = f.location_page;
    }
    if (
      clauseUid === null &&
      typeof f.location_clause_ref === "string" &&
      f.location_clause_ref.trim().length > 0
    ) {
      clauseUid = f.location_clause_ref;
    }
    if (page !== null && clauseUid !== null) break;
  }

  return { page, clauseUid };
}

function firstNonEmptyEvidence(items: string[] | undefined): string | null {
  if (!items) return null;
  for (const item of items) {
    if (typeof item === "string" && item.trim().length > 0) {
      return item.trim();
    }
  }
  return null;
}

// -------------------------------------------------------------
// Synthetic legacy MatrixCellDTO from V1 drawer + cell values
// -------------------------------------------------------------

/**
 * Синтезирует legacy-совместимый MatrixCellDTO из V1 drawer content.
 *
 * Мы НЕ выдумываем бизнес-семантику. Все поля, которых V1 не даёт,
 * заполняются безопасными нейтральными значениями:
 *   severity      = ""    (пустая строка — legacy union допускает string)
 *   qc_status     = null
 *   confidence    = null
 *   extracted     = []
 *   qc_by/qc_comment/qc_at = null
 *   conditional_check_triggered = false
 *   trigger_name = null
 *   segments     = null
 *   chunk_*      = null
 *
 * result           = review_status ?? cell_state (просто string-passthrough)
 * snippet          = первый непустой evidence_item
 * page/clause_uid  = первые непустые из drawer.fields
 * display_text     = drawer.display_text
 * review_status    = drawer.review_status
 * review_message   = drawer.review_message
 * needs_manual_review = false (V1 контракт этого поля не имеет)
 * ui_mode          = null    (V1 контракт этого поля не имеет)
 */
function buildLegacyCellFromDrawer(
  drawer: DDGridV1DrawerContentDTO,
): MatrixCellDTO {
  const loc = extractFirstLocation(drawer.fields);
  const snippet = firstNonEmptyEvidence(drawer.evidence_items);
  const reason = resolveDDGridV1DrawerReason(drawer);

  const result: string = drawer.review_status ?? drawer.cell_state ?? "";

  const cell: MatrixCellDTO = {
    result,
    severity: "",

    snippet: snippet ?? "",
    page: loc.page,
    clause_uid: loc.clauseUid,

    extracted: [],

    confidence: null,
    qc_status: null,

    qc_by: null,
    qc_comment: null,
    qc_at: null,

    conditional_check_triggered: false,
    trigger_name: null,

    // Canonical display semantics
    display_text: drawer.display_text ?? reason.text ?? null,
    review_status: drawer.review_status ?? null,
    review_message: drawer.review_message ?? null,
    needs_manual_review: false,
    ui_mode: null,

    // SegmentProvenance — V1 не различает сегменты
    segment_id: null,
    segment_title: null,
    segment_type: null,
    segment_order: null,
    is_primary_segment: null,
    chunk_id: null,
    chunk_index: null,
  };

  return cell;
}

/**
 * Возвращает true, если для (documentId, checkId) в V1-модели
 * достаточно данных, чтобы создать legacy finding.
 *
 * Универсальное правило:
 * - есть drawer_content для этой пары → finding создаётся;
 * - иначе — не создаётся (legacy UI такие никогда не рендерил как findings).
 *
 * cell_values без drawer_content сами по себе не поднимают finding,
 * потому что legacy finding по контракту требует review-context (result/
 * severity/snippet/qc_status), а без drawer_content их синтезировать
 * корректно нельзя.
 */
function findDrawerForPair(
  model: DDGridV1DerivedModel,
  documentId: string,
  checkId: string,
): DDGridV1DrawerContentDTO | null {
  const perDoc = model.drawerContents[documentId];
  if (!perDoc) return null;
  return perDoc[checkId] ?? null;
}

// -------------------------------------------------------------
// Row aggregation (universal counters based on cell_values)
// -------------------------------------------------------------

interface RowCellCounters {
  totalCritical: number;
  totalHigh: number;
  totalMedium: number;
  totalUnclear: number;
}

/**
 * V1 не имеет severity/unclear на уровне ячеек. Возвращаем нули.
 * Не хардкодим "error = critical" и "not_defined = high", потому что
 * это продуктовое решение, а не факт из контракта.
 */
function zeroCounters(): RowCellCounters {
  return {
    totalCritical: 0,
    totalHigh: 0,
    totalMedium: 0,
    totalUnclear: 0,
  };
}

function buildRow(
  v1Row: DDGridV1MatrixRow,
  cellsByCheckId: Record<string, MatrixCellDTO | undefined>,
): ReviewGridRow {
  const counters = zeroCounters();

  return {
    rowId: buildLegacyRowId(v1Row.documentId),

    documentId: v1Row.documentId,
    documentName: v1Row.filename || "[no name]",
    docType: v1Row.docType ?? null,
    folderPath: v1Row.folderPath ?? null,

    // Segments отсутствуют в V1 контракте — честно null.
    segmentId: null,
    segmentTitle: null,
    segmentType: null,
    segmentOrder: null,
    isPrimarySegment: null,

    classificationLevel: null,
    classificationConfidence: null,
    requiresManualReview: false,

    isMultiDocument: false,
    segmentCount: undefined,
    primarySegmentLabel: null,

    ...counters,

    cellsByCheckId,
  };
}

// -------------------------------------------------------------
// Finding builder
// -------------------------------------------------------------

function buildFinding(
  v1Row: DDGridV1MatrixRow,
  check: CheckSummary,
  drawer: DDGridV1DrawerContentDTO,
): ReviewFinding {
  const cell = buildLegacyCellFromDrawer(drawer);
  const reason = resolveDDGridV1DrawerReason(drawer);

  return {
    findingId: buildLegacyFindingId(v1Row.documentId, check.checkId),
    rowId: buildLegacyRowId(v1Row.documentId),

    documentId: v1Row.documentId,
    documentName: v1Row.filename || "[no name]",
    docType: v1Row.docType ?? null,
    folderPath: v1Row.folderPath ?? null,

    segmentId: null,
    segmentTitle: null,
    segmentType: null,
    segmentOrder: null,
    isPrimarySegment: null,

    checkId: check.checkId,
    checkName: check.checkName,
    origin: check.origin,
    checkSeverityBaseline: null,

    result: cell.result,
    severity: null,
    qcStatus: null,
    confidence: null,

    snippet: cell.snippet || null,
    page: cell.page,
    clauseUid: cell.clause_uid,

    conditionalTriggered: false,
    triggerName: null,

    chunkId: null,
    chunkIndex: null,

    displayText: cell.display_text ?? reason.text ?? null,
    reviewStatus: cell.review_status ?? null,
    reviewMessage: cell.review_message ?? null,
    needsManualReview: false,
    uiMode: null,

    cell,
  };
}

// -------------------------------------------------------------
// Public: adapt V1 → legacy derived data
// -------------------------------------------------------------

/**
 * Основная функция адаптера: превращает V1 derived model в
 * legacy ReviewGridDerivedData (rows / findings / columns / stats / фильтры).
 *
 * Полученный объект можно передавать напрямую в:
 * - ReviewGridFilters (availableDocTypes, availableOrigins)
 * - filterReviewFindings / filterReviewRows
 * - ReviewQcBulkActions (через getReviewQcCapability / getSelectedReviewFindings)
 * - ReviewExportButtons (через buildReviewExportRows)
 *
 * без единой правки в legacy файлах.
 */
export function adaptDDGridV1ToLegacyReview(
  model: DDGridV1DerivedModel,
): ReviewGridDerivedData {
  const uniqueChecks = collectUniqueChecks(model);

  // 1. Columns
  const columns: ReviewCheckColumn[] = uniqueChecks.map((c) => ({
    checkId: c.checkId,
    checkName: c.checkName,
    origin: c.origin,
    severity: null,
  }));

  // 2. Findings + cellsByCheckId
  const findings: ReviewFinding[] = [];
  const cellsByRow = new Map<string, Record<string, MatrixCellDTO | undefined>>();

  for (const v1Row of model.rows) {
    const cellMap: Record<string, MatrixCellDTO | undefined> = {};

    for (const check of uniqueChecks) {
      const drawer = findDrawerForPair(model, v1Row.documentId, check.checkId);
      if (!drawer) {
        cellMap[check.checkId] = undefined;
        continue;
      }
      const finding = buildFinding(v1Row, check, drawer);
      findings.push(finding);
      cellMap[check.checkId] = finding.cell;
    }

    cellsByRow.set(v1Row.documentId, cellMap);
  }

  // 3. Rows
  const rows: ReviewGridRow[] = model.rows.map((v1Row) =>
    buildRow(v1Row, cellsByRow.get(v1Row.documentId) ?? {}),
  );

  // 4. Stats
  const stats = buildStats(rows, findings, columns);

  // 5. Filter dictionaries
  const availableDocTypes = collectAvailableDocTypes(rows);
  const availableOrigins = collectAvailableOrigins(columns);

  return {
    columns,
    rows,
    findings,
    stats,
    availableDocTypes,
    availableOrigins,
  };
}

// -------------------------------------------------------------
// Stats + dictionaries
// -------------------------------------------------------------

function buildStats(
  rows: ReviewGridRow[],
  findings: ReviewFinding[],
  columns: ReviewCheckColumn[],
): ReviewGridStats {
  const uniqueDocs = new Set<string>();
  for (const row of rows) uniqueDocs.add(row.documentId);

  return {
    documentsCount: uniqueDocs.size,
    rowsCount: rows.length,
    findingsCount: findings.length,
    checksCount: columns.length,

    // V1 контракт не предоставляет severity/unclear/qc — оставляем нули.
    criticalCount: 0,
    highCount: 0,
    mediumCount: 0,
    unclearCount: 0,
    noQcCount: findings.length,
  };
}

function collectAvailableDocTypes(rows: ReviewGridRow[]): string[] {
  const s = new Set<string>();
  for (const row of rows) {
    if (row.docType) s.add(row.docType);
  }
  return Array.from(s).sort();
}

function collectAvailableOrigins(columns: ReviewCheckColumn[]): string[] {
  const s = new Set<string>();
  for (const c of columns) {
    if (c.origin) s.add(c.origin);
  }
  return Array.from(s).sort();
}

// -------------------------------------------------------------
// Public: cell values lookup (для UI, отдельно от legacy adapter)
// -------------------------------------------------------------

/**
 * Утилита: вернуть V1 cell value для (documentId, columnId).
 * Не путать с legacy cellsByCheckId — эта функция читает V1 напрямую,
 * без прохождения через legacy MatrixCellDTO.
 */
export function getDDGridV1CellValue(
  model: DDGridV1DerivedModel,
  documentId: string,
  columnId: string,
): DDGridV1CellValueDTO | null {
  const perDoc = model.cellValues[documentId];
  if (!perDoc) return null;
  return perDoc[columnId] ?? null;
}

// Экспортируем внутренние id-строители — они понадобятся page-компоненту
// V1.12.4, чтобы строить ReviewSelectionItem согласованно с адаптером.
export const ddGridV1LegacyIds = {
  rowId: buildLegacyRowId,
  findingId: buildLegacyFindingId,
} as const;


