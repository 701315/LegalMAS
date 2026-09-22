// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.selectors.ts
// Селекторы, превращающие DDGridV1ResponseDTO в UI-модель.
//
// Правила:
// - никаких хардкодов конкретных check_id / column_id / doc_type;
// - source of truth по составу колонок — global_groups и doc_type_classes,
//   потому что column_id может дублироваться в column_registry внутри
//   одного check-а (наблюдаемое поведение backend, зафиксировано в snapshot);
// - все ключи UI (runtimeKey, nodeKey, rowId, cellKey) строятся детерминированно.
// =============================================================

import type {
  DDGridV1CellState,
  DDGridV1CellValueDTO,
  DDGridV1CheckDTO,
  DDGridV1ColumnDTO,
  DDGridV1DocTypeClassDTO,
  DDGridV1DocTypeDTO,
  DDGridV1DocumentMetaDTO,
  DDGridV1DrawerContentDTO,
  DDGridV1GlobalGroupDTO,
  DDGridV1ResponseDTO,
} from "../../../types/dealReview";

import {
  classifyDDGridV1LocationAvailability,
  formatDDGridV1CellText,
} from "./ddGridV1.formatters";

import type {
  DDGridV1CellView,
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
  DDGridV1DocTypeClassNode,
  DDGridV1DocTypeNode,
  DDGridV1GlobalGroupNode,
  DDGridV1MatrixRow,
  DDGridV1RuntimeColumn,
  DDGridV1Stats,
} from "./ddGridV1.types";

// -------------------------------------------------------------
// Sorting helpers
// -------------------------------------------------------------

function byDisplayOrder<T extends { display_order: number }>(a: T, b: T): number {
  return (a.display_order ?? 0) - (b.display_order ?? 0);
}

function sortedGlobalGroups(
  groups: DDGridV1GlobalGroupDTO[],
): DDGridV1GlobalGroupDTO[] {
  return [...(groups ?? [])].sort(byDisplayOrder);
}

function sortedDocTypeClasses(
  classes: DDGridV1DocTypeClassDTO[],
): DDGridV1DocTypeClassDTO[] {
  return [...(classes ?? [])].sort(byDisplayOrder);
}

function sortedChecks(checks: DDGridV1CheckDTO[]): DDGridV1CheckDTO[] {
  return [...(checks ?? [])].sort(byDisplayOrder);
}

function sortedColumns(columns: DDGridV1ColumnDTO[]): DDGridV1ColumnDTO[] {
  return [...(columns ?? [])].sort(byDisplayOrder);
}

// -------------------------------------------------------------
// Runtime columns
// -------------------------------------------------------------

/**
 * Универсальный строитель runtime keys.
 *
 * Формат:
 *   {scope}|{containerPath}|{checkId}|{columnId}|{indexInCheck}
 *
 * Индекс внутри check устраняет коллизии из-за дубликатов column_id
 * (наблюдаемо в snapshot: несколько DrawerField с одинаковым column_id).
 */
function buildRuntimeKey(
  scope: "global" | "docType",
  containerPath: string[],
  checkId: string,
  columnId: string,
  indexInCheck: number,
): string {
  return [scope, containerPath.join(">"), checkId, columnId, String(indexInCheck)].join("|");
}

function buildCheckNodeKey(
  scope: "global" | "docType",
  containerPath: string[],
  checkId: string,
): string {
  return [scope, containerPath.join(">"), "check", checkId].join("|");
}

function buildRuntimeColumnsForCheck(
  check: DDGridV1CheckDTO,
  scope: "global" | "docType",
  containerPath: string[],
  applicableDocTypeCodes: string[],
): DDGridV1RuntimeColumn[] {
  const cols = sortedColumns(check.columns ?? []);
  return cols.map((column, indexInCheck) => ({
    runtimeKey: buildRuntimeKey(
      scope,
      containerPath,
      check.check_id,
      column.column_id,
      indexInCheck,
    ),
    scope,
    containerPath,
    applicableDocTypeCodes,
    checkId: check.check_id,
    indexInCheck,
    column,
  }));
}

function buildCheckNode(
  check: DDGridV1CheckDTO,
  scope: "global" | "docType",
  containerPath: string[],
  applicableDocTypeCodes: string[],
): DDGridV1CheckNode {
  return {
    nodeKey: buildCheckNodeKey(scope, containerPath, check.check_id),
    checkId: check.check_id,
    checkName: check.check_name,
    displayOrder: check.display_order ?? 0,
    columns: buildRuntimeColumnsForCheck(
      check,
      scope,
      containerPath,
      applicableDocTypeCodes,
    ),
    check,
  };
}

// -------------------------------------------------------------
// Global groups
// -------------------------------------------------------------

function buildGlobalGroupNode(
  group: DDGridV1GlobalGroupDTO,
): DDGridV1GlobalGroupNode {
  const containerPath = [group.group_id];
  const checks = sortedChecks(group.checks ?? []).map((check) =>
    buildCheckNode(check, "global", containerPath, /* applicable */ []),
  );

  return {
    nodeKey: ["global", "group", group.group_id].join("|"),
    groupId: group.group_id,
    label: group.label,
    displayOrder: group.display_order ?? 0,
    checks,
    globalGroup: group,
  };
}

// -------------------------------------------------------------
// Doc-type classes
// -------------------------------------------------------------

function buildDocTypeNode(
  cls: DDGridV1DocTypeClassDTO,
  docType: DDGridV1DocTypeDTO,
): DDGridV1DocTypeNode {
  const containerPath = [cls.group_id, docType.type_code];
  const applicable = [docType.type_code];
  const checks = sortedChecks(docType.checks ?? []).map((check) =>
    buildCheckNode(check, "docType", containerPath, applicable),
  );

  return {
    nodeKey: ["docType", "type", cls.group_id, docType.type_code].join("|"),
    typeCode: docType.type_code,
    name: docType.name,
    checks,
    docType,
  };
}

function buildDocTypeClassNode(
  cls: DDGridV1DocTypeClassDTO,
): DDGridV1DocTypeClassNode {
  const types = (cls.types ?? []).map((docType) => buildDocTypeNode(cls, docType));
  return {
    nodeKey: ["docType", "class", cls.group_id].join("|"),
    groupId: cls.group_id,
    label: cls.label,
    displayOrder: cls.display_order ?? 0,
    types,
    docTypeClass: cls,
  };
}

// -------------------------------------------------------------
// Rows
// -------------------------------------------------------------

function buildMatrixRow(meta: DDGridV1DocumentMetaDTO): DDGridV1MatrixRow {
  return {
    rowId: `doc:${meta.document_id}`,
    documentId: meta.document_id,
    filename: meta.filename,
    docType: meta.doc_type,
    status: meta.status,
    folderPath: meta.folder_path,
    segmentId: meta.segment_id,
    segmentType: meta.segment_type,
    segmentTitle: meta.segment_title,
    instructionSnapshot: meta.instruction_snapshot ?? null,
    meta,
  };
}

// -------------------------------------------------------------
// Stats
// -------------------------------------------------------------

function computeStats(
  documents: DDGridV1DocumentMetaDTO[],
  runtimeColumns: DDGridV1RuntimeColumn[],
  cellValues: Record<string, Record<string, Record<string, DDGridV1CellValueDTO>>>,
  checksCount: number,
): DDGridV1Stats {
  let definedCount = 0;
  let notDefinedCount = 0;
  let errorCount = 0;

  for (const segmentCells of Object.values(cellValues ?? {})) {
    for (const columnCells of Object.values(segmentCells ?? {})) {
      for (const cell of Object.values(columnCells ?? {})) {
        switch (cell.cell_state) {
          case "defined":
            definedCount += 1;
            break;
          case "not_defined":
            notDefinedCount += 1;
            break;
          case "error":
            errorCount += 1;
            break;
          default:
            break;
        }
      }
    }
  }

  return {
    documentsCount: documents.length,
    checksCount,
    runtimeColumnsCount: runtimeColumns.length,
    definedCellsCount: definedCount,
    notDefinedCellsCount: notDefinedCount,
    errorCellsCount: errorCount,
  };
}

// -------------------------------------------------------------
// Public: derived model
// -------------------------------------------------------------

/**
 * Главный селектор. Строит полную UI-модель из ответа backend.
 * Идемпотентен и не имеет побочных эффектов.
 */
export function selectDDGridV1DerivedModel(
  dto: DDGridV1ResponseDTO | null | undefined,
): DDGridV1DerivedModel {
  if (!dto) {
    return {
      dealId: "",
      runId: "",
      globalGroups: [],
      docTypeClasses: [],
      runtimeColumns: [],
      runtimeColumnsByKey: {},
      rows: [],
      rowsByDocumentId: {},
      drawerContents: {},
      cellValues: {},
      stats: {
        documentsCount: 0,
        checksCount: 0,
        runtimeColumnsCount: 0,
        definedCellsCount: 0,
        notDefinedCellsCount: 0,
        errorCellsCount: 0,
      },
    };
  }

  const globalGroups = sortedGlobalGroups(dto.global_groups).map(buildGlobalGroupNode);
  const docTypeClasses = sortedDocTypeClasses(dto.doc_type_classes).map(
    buildDocTypeClassNode,
  );

  // Плоский список runtime-колонок в порядке появления в UI
  const runtimeColumns: DDGridV1RuntimeColumn[] = [];
  const runtimeColumnsByKey: Record<string, DDGridV1RuntimeColumn> = {};

  const collect = (col: DDGridV1RuntimeColumn) => {
    runtimeColumns.push(col);
    runtimeColumnsByKey[col.runtimeKey] = col;
  };

  for (const group of globalGroups) {
    for (const check of group.checks) {
      for (const col of check.columns) collect(col);
    }
  }
  for (const cls of docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        for (const col of check.columns) collect(col);
      }
    }
  }

  const rows = (dto.documents_meta ?? []).map(buildMatrixRow);
  const rowsByDocumentId: Record<string, DDGridV1MatrixRow> = {};
  for (const row of rows) rowsByDocumentId[row.documentId] = row;

  const uniqueCheckIds = new Set<string>();
  for (const group of globalGroups) {
    for (const check of group.checks) uniqueCheckIds.add(check.checkId);
  }
  for (const cls of docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) uniqueCheckIds.add(check.checkId);
    }
  }

  const stats = computeStats(
    dto.documents_meta ?? [],
    runtimeColumns,
    dto.cell_values ?? {},
    uniqueCheckIds.size,
  );

  return {
    dealId: dto.deal_id,
    runId: dto.run_id,
    globalGroups,
    docTypeClasses,
    runtimeColumns,
    runtimeColumnsByKey,
    rows,
    rowsByDocumentId,
    drawerContents: dto.drawer_contents ?? {},
    cellValues: dto.cell_values ?? {},
    stats,
  };
}

// -------------------------------------------------------------
// Public: cell resolution
// -------------------------------------------------------------

/**
 * Универсальное разрешение ячейки для (row, runtimeColumn).
 *
 * Порядок:
 *   1. если cell_values[docId][columnId] есть → используем его напрямую;
 *   2. иначе, если колонка привязана к конкретному type_code (docType scope)
 *      и doc_type документа не входит в applicableDocTypeCodes → not_applicable;
 *   3. иначе → not_executed.
 *
 * Форматирование финального текста делегируется formatDDGridV1CellText,
 * классификация location — classifyDDGridV1LocationAvailability.
 */
export function resolveDDGridV1CellView(
  row: DDGridV1MatrixRow,
  runtimeColumn: DDGridV1RuntimeColumn,
  cellValues: Record<string, Record<string, Record<string, DDGridV1CellValueDTO>>>,
  t?: (key: string) => string, // 🌟 Добавили опциональный транслятор
): DDGridV1CellView {
  const cellKey = `${row.rowId}::${runtimeColumn.runtimeKey}`;
  
  // 3-уровневый lookup: doc_id → segment_id → column_id
  // segment_id берём из row, для single-segment = "_default"
  const segmentId = row.segmentId ?? "_default";
  const perDoc = cellValues[row.documentId];
  const perSegment = perDoc ? perDoc[segmentId] : undefined;
  const rawCell = perSegment ? perSegment[runtimeColumn.column.column_id] ?? null : null;

  let effectiveState: DDGridV1CellState;
  let effectiveRawCell: DDGridV1CellValueDTO | null = rawCell;

  if (rawCell) {
    effectiveState = rawCell.cell_state;
  } else {
    // Применимость check гарантируется планировщиком на бэкенде.
    // Если plan_item отсутствует — ячейка не создаётся.
    // Для docType-scoped колонок которые не применимы к doc_type — not_executed.
    effectiveState = "not_executed";
    effectiveRawCell = null;
  }

  const displayText = formatDDGridV1CellText(
    effectiveState,
    effectiveRawCell,
    runtimeColumn.column,
    t, // 🌟 Пробрасываем t дальше
  );

  const locationAvailability = effectiveRawCell
    ? classifyDDGridV1LocationAvailability({
        location_source: effectiveRawCell.location_source,
        anchor_method: effectiveRawCell.anchor_method ?? null,
      })
    : "unavailable";

  return {
    cellKey,
    cellState: effectiveState,
    displayText,
    format: runtimeColumn.column.format,
    locationAvailability,
    rawCell: effectiveRawCell,
    locationConfidence: effectiveRawCell?.location_confidence ?? null,
  };
}

// -------------------------------------------------------------
// Public: drawer lookup
// -------------------------------------------------------------

/**
 * Возвращает drawer content для (documentId, checkId) или null.
 * Никогда не бросает.
 */
export function getDDGridV1DrawerContent(
  drawerContents: Record<string, Record<string, Record<string, DDGridV1DrawerContentDTO>>>,
  documentId: string,
  segmentId: string,
  checkId: string,
): DDGridV1DrawerContentDTO | null {
  const perDoc = drawerContents[documentId];
  if (!perDoc) return null;
  const perSegment = perDoc[segmentId];
  if (!perSegment) return null;
  return perSegment[checkId] ?? null;
}


