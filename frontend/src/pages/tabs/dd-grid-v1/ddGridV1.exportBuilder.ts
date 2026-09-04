// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.exportBuilder.ts
// Единый source of truth для экспорта DD Grid V1.
//
// Правила:
// - экспорт всегда идентичен тому, что видит юрист на экране;
// - список колонок = базовые + выбранные extra columns;
// - фильтры применяются те же (visibleCheckIds, includePassResults);
// - никаких хардкодов бизнес-логики.
//
// i18n: утилита работает через передаваемый tFn, fallback — English.
// =============================================================

import type { DDGridV1DrawerContentDTO } from "../../../types/dealReview";

import {
  resolveDDGridV1Confidence,
  resolveDDGridV1DetectionLevel,
  resolveDDGridV1Observability,
  resolveDDGridV1QcAuditInfo,
  resolveDDGridV1QualityFlags,
} from "./ddGridV1.drawer";

import type {
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
  DDGridV1MatrixRow,
} from "./ddGridV1.types";

// -------------------------------------------------------------
// Translation helper interface
// -------------------------------------------------------------

type TFunction = (key: string, options?: Record<string, any>) => string;

// Default fallback translator (English)
const defaultT: TFunction = (key, options) => {
  const defaults: Record<string, string> = {
    "unnamedDocument": "[unnamed]",
    "columns.rowNumber": "№",
    "columns.document": "Document",
    "columns.docType": "Document type",
    "columns.check": "Check",
    "columns.result": "Result",
    "columns.status": "Status",
    "columns.location": "Location",
    "columns.parameter": "Parameter",
    "columns.value": "Value",
    "reviewStatus.empty": "—",
    "reviewStatus.needs_review": "Needs review",
    "reviewStatus.no_issue_detected": "No issues detected",
    "reviewStatus.unclear": "Unclear",
    "qc.approved": "Approved",
    "qc.rejected": "Rejected",
    "qc.needs_review": "Needs review",
    "matrix.unknownCheck": "Unknown check",
    "drawer.cellStateLabels.error": "⚠ Error",
    "extra.detectionLevel.label": "Analysis method",
    "extra.qcStatus.label": "QC Status",
    "extra.confidence.label": "Confidence",
    "extra.qualityFlags.label": "Warnings",
    "extra.agentName.label": "Agent name",
    "extra.modelVersion.label": "Model version",
    "extra.executionTime.label": "Execution time",
    "extra.retryAttempts.label": "LLM attempts",
    "extra.inputTokens.label": "Input tokens",
    "extra.outputTokens.label": "Output tokens",
  };
  
  if (key === "location.pageAbbr" && options && typeof options.page === "number") {
    return `p. ${options.page}`;
  }
  
  return defaults[key] ?? String(options?.defaultValue ?? key);
};

// -------------------------------------------------------------
// Column catalog
// -------------------------------------------------------------

/**
 * Один столбец в экспорте.
 * Порядок появления в экспорте определяется порядком в этом массиве.
 */
export interface DDGridV1ExportColumn {
  id: string;
  label: string;
  /** Функция извлечения значения из подготовленной строки. */
  extract: (row: DDGridV1ExportSourceRow) => string;
}

/**
 * Подготовленная строка данных для экспорта.
 * Содержит все необходимые raw-поля без форматирования.
 */
export interface DDGridV1ExportSourceRow {
  documentName: string;
  docType: string;
  checkName: string;
  displayText: string;
  reviewStatusLabel: string;
  locationText: string;

  // Extra — все поля, которые могут понадобиться
  detectionLevel: string;
  qcStatus: string;
  confidenceFormatted: string;
  qualityFlagsText: string;
  agentName: string;
  modelVersion: string;
  executionTime: string;
  retryAttempts: string;
  inputTokens: string;
  outputTokens: string;

  // Метаданные для трассировки (всегда экспортируются в скрытом виде)
  documentId: string;
  checkId: string;
}

// -------------------------------------------------------------
// Review status labels
// -------------------------------------------------------------

function getReviewStatusLabel(
  status: string | null | undefined,
  t: TFunction,
): string {
  if (!status || typeof status !== "string" || status.trim().length === 0) {
    return t("reviewStatus.empty");
  }
  const normalized = status.trim();
  switch (normalized) {
    case "needs_review":
      return t("reviewStatus.needs_review");
    case "no_issue_detected":
    case "ok":
      return t("reviewStatus.no_issue_detected");
    case "unclear":
      return t("reviewStatus.unclear");
    default:
      return normalized;
  }
}

// -------------------------------------------------------------
// Location text
// -------------------------------------------------------------

function buildLocationText(
  drawer: DDGridV1DrawerContentDTO | null,
  t: TFunction,
): string {
  if (!drawer) return "";

  for (const field of drawer.fields ?? []) {
    const parts: string[] = [];
    if (typeof field.location_page === "number") {
      parts.push(t("location.pageAbbr", { page: field.location_page }));
    }
    if (
      typeof field.location_clause_ref === "string" &&
      field.location_clause_ref.trim().length > 0
    ) {
      parts.push(field.location_clause_ref.trim());
    }
    if (parts.length > 0) {
      return parts.join(" · ");
    }
  }

  return "";
}

// -------------------------------------------------------------
// Column definitions builder
// -------------------------------------------------------------

function getBaseExportColumns(t: TFunction): readonly DDGridV1ExportColumn[] {
  return [
    {
      id: "rowNumber",
      label: t("columns.rowNumber"),
      extract: () => "",
    },
    {
      id: "documentName",
      label: t("columns.document"),
      extract: (r) => r.documentName,
    },
    {
      id: "docType",
      label: t("columns.docType"),
      extract: (r) => r.docType,
    },
    {
      id: "checkName",
      label: t("columns.check"),
      extract: (r) => r.checkName,
    },
    {
      id: "displayText",
      label: t("columns.result"),
      extract: (r) => r.displayText,
    },
    {
      id: "reviewStatus",
      label: t("columns.status"),
      extract: (r) => r.reviewStatusLabel,
    },
    {
      id: "locationText",
      label: t("columns.location"),
      extract: (r) => r.locationText,
    },
  ];
}

function getExtraExportColumns(t: TFunction): Record<string, DDGridV1ExportColumn> {
  return {
    detectionLevel: {
      id: "detectionLevel",
      label: t("extra.detectionLevel.label"),
      extract: (r) => r.detectionLevel,
    },
    qcStatus: {
      id: "qcStatus",
      label: t("extra.qcStatus.label"),
      extract: (r) => r.qcStatus,
    },
    confidence: {
      id: "confidence",
      label: t("extra.confidence.label"),
      extract: (r) => r.confidenceFormatted,
    },
    qualityFlags: {
      id: "qualityFlags",
      label: t("extra.qualityFlags.label"),
      extract: (r) => r.qualityFlagsText,
    },
    agentName: {
      id: "agentName",
      label: t("extra.agentName.label"),
      extract: (r) => r.agentName,
    },
    modelVersion: {
      id: "modelVersion",
      label: t("extra.modelVersion.label"),
      extract: (r) => r.modelVersion,
    },
    executionTime: {
      id: "executionTime",
      label: t("extra.executionTime.label"),
      extract: (r) => r.executionTime,
    },
    retryAttempts: {
      id: "retryAttempts",
      label: t("extra.retryAttempts.label"),
      extract: (r) => r.retryAttempts,
    },
    inputTokens: {
      id: "inputTokens",
      label: t("extra.inputTokens.label"),
      extract: (r) => r.inputTokens,
    },
    outputTokens: {
      id: "outputTokens",
      label: t("extra.outputTokens.label"),
      extract: (r) => r.outputTokens,
    },
  };
}

const EXTRA_EXPORT_COLUMN_ORDER: readonly string[] = [
  "detectionLevel",
  "qcStatus",
  "confidence",
  "qualityFlags",
  "agentName",
  "modelVersion",
  "executionTime",
  "retryAttempts",
  "inputTokens",
  "outputTokens",
] as const;

// -------------------------------------------------------------
// Public API
// -------------------------------------------------------------

/**
 * Строит финальный список колонок для экспорта.
 * Учитывает выбор пользователя.
 */
export function buildDDGridV1ExportColumns(
  visibleExtraColumnIds: readonly string[] | undefined,
  t: TFunction = defaultT,
): DDGridV1ExportColumn[] {
  const columns: DDGridV1ExportColumn[] = [...getBaseExportColumns(t)];

  const visibleExtras = new Set(visibleExtraColumnIds ?? []);
  if (visibleExtras.size === 0) return columns;

  const extraColumnsMap = getExtraExportColumns(t);
  for (const id of EXTRA_EXPORT_COLUMN_ORDER) {
    if (!visibleExtras.has(id)) continue;
    const col = extraColumnsMap[id];
    if (col) columns.push(col);
  }

  return columns;
}

/**
 * Формирует source rows для экспорта из V1 модели.
 * Применяет ТЕ ЖЕ фильтры, что и UI (visibleCheckIds, includePassResults).
 */
export function buildDDGridV1ExportRows(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
  includePassResults?: boolean;
  t?: TFunction;
}): DDGridV1ExportSourceRow[] {
  const { model, visibleCheckIds, includePassResults = true, t = defaultT } = params;

  const allChecks: DDGridV1CheckNode[] = [];
  const seenCheckIds = new Set<string>();

  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      if (!check.checkId) continue;
      if (!seenCheckIds.has(check.checkId)) {
        seenCheckIds.add(check.checkId);
        allChecks.push(check);
      }
    }
  }
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        if (!check.checkId) continue;
        if (!seenCheckIds.has(check.checkId)) {
          seenCheckIds.add(check.checkId);
          allChecks.push(check);
        }
      }
    }
  }

  const visibleCheckSet = visibleCheckIds ? new Set(visibleCheckIds) : null;

  const result: DDGridV1ExportSourceRow[] = [];

  for (const v1Row of model.rows) {
    for (const check of allChecks) {
      if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) continue;

      const segmentId = v1Row.segmentId ?? "_default";
      const drawer =
        model.drawerContents[v1Row.documentId]?.[segmentId]?.[check.checkId] ?? null;
      if (!drawer) continue;

      if (
        !includePassResults &&
        (drawer.review_status === "no_issue_detected" ||
          drawer.review_status === "ok")
      ) {
        continue;
      }

      result.push(buildExportSourceRow(v1Row, check, drawer, t));
    }
  }

  return result;
}

/**
 * Собирает одну готовую source row.
 */
function buildExportSourceRow(
  v1Row: DDGridV1MatrixRow,
  check: DDGridV1CheckNode,
  drawer: DDGridV1DrawerContentDTO,
  t: TFunction,
): DDGridV1ExportSourceRow {
  const detectionLevelInfo = resolveDDGridV1DetectionLevel(drawer);
  const confidenceInfo = resolveDDGridV1Confidence(drawer);
  const qualityFlags = resolveDDGridV1QualityFlags(drawer);
  const qcAuditInfo = resolveDDGridV1QcAuditInfo(drawer);
  const observability = resolveDDGridV1Observability(drawer);

  const qcStatusLabel =
    qcAuditInfo.status && qcAuditInfo.status !== "pending"
      ? {
          approved: t("qc.approved"),
          rejected: t("qc.rejected"),
          needs_review: t("qc.needs_review"),
        }[qcAuditInfo.status] ?? qcAuditInfo.status
      : "";

  return {
    documentName: v1Row.filename || t("unnamedDocument"),
    docType: v1Row.docType || "—",
    checkName: check.checkName || check.checkId,
    displayText: drawer.display_text?.trim() || "",
    reviewStatusLabel: getReviewStatusLabel(drawer.review_status, t),
    locationText: buildLocationText(drawer, t),

    detectionLevel: detectionLevelInfo.badge ?? "",
    qcStatus: qcStatusLabel,
    confidenceFormatted: confidenceInfo.formatted ?? "",
    qualityFlagsText: qualityFlags.map((f) => f.label).join(", "),
    agentName: observability.agentName ?? "",
    modelVersion: observability.modelVersion ?? "",
    executionTime: observability.executionTimeFormatted ?? "",
    retryAttempts:
      observability.retryAttempts !== null
        ? String(observability.retryAttempts)
        : "",
    inputTokens:
      observability.inputTokens !== null
        ? observability.inputTokens.toLocaleString()
        : "",
    outputTokens:
      observability.outputTokens !== null
        ? observability.outputTokens.toLocaleString()
        : "",

    documentId: v1Row.documentId,
    checkId: check.checkId,
  };
}

/**
 * Общий result type для list export — плоский формат.
 */
export interface DDGridV1ExportTable {
  headers: string[];
  rows: string[][];
  rowCount: number;
}

/**
 * Structured header cell для matrix export.
 * colSpan = 1 по умолчанию; если > 1 — Excel/Word/PDF объединяют колонки.
 */
export interface DDGridV1MatrixHeaderCell {
  label: string;
  colSpan: number;
}

/**
 * Result type для matrix export с иерархическими заголовками.
 */
export interface DDGridV1MatrixExportTable {
  pinnedHeaders: string[];
  headerRows: [
    DDGridV1MatrixHeaderCell[],
    DDGridV1MatrixHeaderCell[],
    DDGridV1MatrixHeaderCell[],
  ];
  leafHeaders: string[];
  rows: string[][];
  pinnedColumnCount: number;
  rowCount: number;
}

/**
 * Строит list export — плоская таблица findings.
 * Каждая строка = одна пара (документ, проверка).
 * Используется в list mode.
 */
export function buildDDGridV1ListExportTable(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
  includePassResults?: boolean;
  visibleExtraColumnIds?: readonly string[];
  t?: TFunction;
}): DDGridV1ExportTable {
  const t = params.t ?? defaultT;
  const columns = buildDDGridV1ExportColumns(params.visibleExtraColumnIds, t);
  const sourceRows = buildDDGridV1ExportRows({
    model: params.model,
    visibleCheckIds: params.visibleCheckIds,
    includePassResults: params.includePassResults,
    t,
  });

  const headers = columns.map((c) => c.label);
  const rowNumberColumnIndex = columns.findIndex((c) => c.id === "rowNumber");

  const rows = sourceRows.map((r, index) => {
    const rowValues = columns.map((c) => c.extract(r));
    if (rowNumberColumnIndex >= 0) {
      rowValues[rowNumberColumnIndex] = String(index + 1);
    }
    return rowValues;
  });

  return {
    headers,
    rows,
    rowCount: rows.length,
  };
}

export const buildDDGridV1ExportTable = buildDDGridV1ListExportTable;

/**
 * Строит matrix export — двумерная таблица с иерархическими заголовками.
 */
export function buildDDGridV1MatrixExportTable(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
  t?: TFunction;
}): DDGridV1MatrixExportTable {
  const { model, visibleCheckIds, t = defaultT } = params;
  const visibleCheckSet = visibleCheckIds ? new Set(visibleCheckIds) : null;

  interface MatrixColumn {
    scopeGroupLabel: string;
    checkName: string;
    columnLabel: string;
    extract: (row: DDGridV1MatrixRow) => string;
  }

  const matrixColumns: MatrixColumn[] = [];
  const seenCheckIds = new Set<string>();

  const processCheck = (
    check: DDGridV1CheckNode,
    scopeGroupLabel: string,
  ) => {
    if (!check.checkId) return;
    if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) return;
    if (seenCheckIds.has(check.checkId)) return;
    seenCheckIds.add(check.checkId);

    const checkName = check.checkName || check.checkId || t("matrix.unknownCheck");

    for (const runtimeColumn of check.columns) {
      const columnLabel = runtimeColumn.column.label;

      matrixColumns.push({
        scopeGroupLabel,
        checkName,
        columnLabel,
        extract: (row) => {
          const segmentId = row.segmentId ?? "_default";
          const perDoc = model.cellValues[row.documentId];
          const perSegment = perDoc ? perDoc[segmentId] : undefined;
          const rawCell = perSegment ? perSegment[runtimeColumn.column.column_id] ?? null : null;

          if (!rawCell) {
            return "—";
          }

          switch (rawCell.cell_state) {
            case "error":
              return t("drawer.cellStateLabels.error");
            case "not_defined":
            case "not_executed":
              return "—";
            case "defined":
            default:
              return rawCell.display_value || "";
          }
        },
      });
    }
  };

  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      processCheck(check, group.label);
    }
  }

  for (const cls of model.docTypeClasses) {
    for (const tType of cls.types) {
      const scopeLabel = `${cls.label} · ${tType.name}`;
      for (const check of tType.checks) {
        processCheck(check, scopeLabel);
      }
    }
  }

  const buildMergedRow = (
    getKey: (col: MatrixColumn) => string,
  ): DDGridV1MatrixHeaderCell[] => {
    const cells: DDGridV1MatrixHeaderCell[] = [];
    let currentKey: string | null = null;
    let currentCell: DDGridV1MatrixHeaderCell | null = null;

    for (const col of matrixColumns) {
      const key = getKey(col);
      if (key === currentKey && currentCell) {
        currentCell.colSpan += 1;
      } else {
        currentCell = { label: key, colSpan: 1 };
        cells.push(currentCell);
        currentKey = key;
      }
    }

    return cells;
  };

  const scopeRow = buildMergedRow((col) => col.scopeGroupLabel);
  const checkRow = buildMergedRow(
    (col) => `${col.scopeGroupLabel}||${col.checkName}`,
  );
  
  const checkRowFinal: DDGridV1MatrixHeaderCell[] = [];
  let colIndex = 0;
  for (const cell of checkRow) {
    checkRowFinal.push({
      label: matrixColumns[colIndex].checkName,
      colSpan: cell.colSpan,
    });
    colIndex += cell.colSpan;
  }

  const columnRow: DDGridV1MatrixHeaderCell[] = matrixColumns.map((col) => ({
    label: col.columnLabel,
    colSpan: 1,
  }));

  const pinnedHeaders = [
    t("columns.rowNumber"),
    t("columns.document"),
    t("columns.docType")
  ];
  const pinnedColumnCount = pinnedHeaders.length;

  const rows: string[][] = model.rows.map((row, index) => {
    const rowValues: string[] = [
      String(index + 1),
      row.filename || t("unnamedDocument"),
      row.docType || "—",
    ];
    for (const col of matrixColumns) {
      rowValues.push(col.extract(row));
    }
    return rowValues;
  });

  const leafHeaders = [
    ...pinnedHeaders,
    ...matrixColumns.map((c) => c.columnLabel),
  ];

  return {
    pinnedHeaders,
    headerRows: [scopeRow, checkRowFinal, columnRow],
    leafHeaders,
    rows,
    pinnedColumnCount,
    rowCount: rows.length,
  };
}

// =============================================================
// SECTIONED export helpers (Layout 2 & 3)
// =============================================================

export interface DDGridV1ExportSection {
  title: string;
  subtitle?: string;
  headers: string[];
  rows: string[][];
}

export interface DDGridV1SectionedExportTable {
  sections: DDGridV1ExportSection[];
  totalRowCount: number;
  maxColumnCount: number;
}

/**
 * Строит sectioned export: одна секция на документ.
 */
export function buildDDGridV1DocumentSectionedExportTable(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
  t?: TFunction;
}): DDGridV1SectionedExportTable {
  const { model, visibleCheckIds, t = defaultT } = params;
  const visibleCheckSet = visibleCheckIds ? new Set(visibleCheckIds) : null;

  interface CheckWithScope {
    check: DDGridV1CheckNode;
    scopeGroupLabel: string;
  }

  const allChecks: CheckWithScope[] = [];
  const seenCheckIds = new Set<string>();

  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      if (!check.checkId) continue;
      if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) continue;
      if (seenCheckIds.has(check.checkId)) continue;
      seenCheckIds.add(check.checkId);
      allChecks.push({ check, scopeGroupLabel: group.label });
    }
  }
  for (const cls of model.docTypeClasses) {
    for (const tType of cls.types) {
      for (const check of tType.checks) {
        if (!check.checkId) continue;
        if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) continue;
        if (seenCheckIds.has(check.checkId)) continue;
        seenCheckIds.add(check.checkId);
        allChecks.push({
          check,
          scopeGroupLabel: `${cls.label} · ${tType.name}`,
        });
      }
    }
  }

  const sections: DDGridV1ExportSection[] = [];
  let totalRowCount = 0;

  for (const v1Row of model.rows) {
    const rows: string[][] = [];

    for (const { check, scopeGroupLabel } of allChecks) {
      const segmentId = v1Row.segmentId ?? "_default";
      const drawer =
        model.drawerContents[v1Row.documentId]?.[segmentId]?.[check.checkId] ?? null;
      if (!drawer) continue;

      const checkName = check.checkName || check.checkId;

      for (const runtimeColumn of check.columns) {
        const perDoc = model.cellValues[v1Row.documentId];
        const perSegment = perDoc ? perDoc[segmentId] : undefined;
        const rawCell = perSegment ? perSegment[runtimeColumn.column.column_id] ?? null : null;

        let value = "";
        if (!rawCell) {
          value = "—";
        } else {
          switch (rawCell.cell_state) {
            case "error":
              value = t("drawer.cellStateLabels.error");
              break;
            case "not_defined":
            case "not_executed":
              value = "—";
              break;
            case "defined":
            default:
              value = rawCell.display_value || "";
          }
        }

        rows.push([
          `${scopeGroupLabel} · ${checkName}`,
          runtimeColumn.column.label,
          value,
        ]);
      }
    }

    if (rows.length === 0) continue;

    sections.push({
      title: v1Row.filename || t("unnamedDocument"),
      subtitle: v1Row.docType || undefined,
      headers: [
        t("columns.check"),
        t("columns.parameter"),
        t("columns.value")
      ],
      rows,
    });
    totalRowCount += rows.length;
  }

  return {
    sections,
    totalRowCount,
    maxColumnCount: 3,
  };
}

/**
 * Строит sectioned export: одна секция на scope group.
 */
export function buildDDGridV1ScopeGroupSectionedExportTable(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
  t?: TFunction;
}): DDGridV1SectionedExportTable {
  const { model, visibleCheckIds, t = defaultT } = params;
  const visibleCheckSet = visibleCheckIds ? new Set(visibleCheckIds) : null;

  interface ScopeSectionPlan {
    title: string;
    subtitle?: string;
    columns: Array<{
      checkName: string;
      columnLabel: string;
      extract: (row: DDGridV1MatrixRow) => string;
    }>;
  }

  const scopeSections: ScopeSectionPlan[] = [];
  const seenCheckIds = new Set<string>();

  const makeExtract = (
    runtimeColumn: DDGridV1CheckNode["columns"][number],
  ) => {
    return (row: DDGridV1MatrixRow): string => {
      const segmentId = row.segmentId ?? "_default";
      const perDoc = model.cellValues[row.documentId];
      const perSegment = perDoc ? perDoc[segmentId] : undefined;
      const rawCell = perSegment ? perSegment[runtimeColumn.column.column_id] ?? null : null;

      if (!rawCell) {
        return "—";
      }
      switch (rawCell.cell_state) {
        case "error":
          return t("drawer.cellStateLabels.error");
        case "not_defined":
        case "not_executed":
          return "—";
        case "defined":
        default:
          return rawCell.display_value || "";
      }
    };
  };

  const processCheck = (
    check: DDGridV1CheckNode,
    sectionPlan: ScopeSectionPlan,
  ) => {
    if (!check.checkId) return;
    if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) return;
    if (seenCheckIds.has(check.checkId)) return;
    seenCheckIds.add(check.checkId);

    const checkName = check.checkName || check.checkId || t("matrix.unknownCheck");

    for (const runtimeColumn of check.columns) {
      sectionPlan.columns.push({
        checkName,
        columnLabel: runtimeColumn.column.label,
        extract: makeExtract(runtimeColumn),
      });
    }
  };

  for (const group of model.globalGroups) {
    const plan: ScopeSectionPlan = {
      title: group.label,
      columns: [],
    };
    for (const check of group.checks) {
      processCheck(check, plan);
    }
    if (plan.columns.length > 0) {
      scopeSections.push(plan);
    }
  }

  for (const cls of model.docTypeClasses) {
    for (const tType of cls.types) {
      const plan: ScopeSectionPlan = {
        title: cls.label,
        subtitle: tType.name,
        columns: [],
      };
      for (const check of tType.checks) {
        processCheck(check, plan);
      }
      if (plan.columns.length > 0) {
        scopeSections.push(plan);
      }
    }
  }

  const sections: DDGridV1ExportSection[] = [];
  let totalRowCount = 0;
  let maxColumnCount = 0;

  for (const plan of scopeSections) {
    const headers = [
      t("columns.rowNumber"),
      t("columns.document"),
      t("columns.docType"),
      ...plan.columns.map((c) => `${c.checkName} — ${c.columnLabel}`),
    ];

    const rows: string[][] = model.rows.map((row, index) => {
      const values: string[] = [
        String(index + 1),
        row.filename || t("unnamedDocument"),
        row.docType || "—",
      ];
      for (const col of plan.columns) {
        values.push(col.extract(row));
      }
      return values;
    });

    sections.push({
      title: plan.title,
      subtitle: plan.subtitle,
      headers,
      rows,
    });

    totalRowCount += rows.length;
    if (headers.length > maxColumnCount) {
      maxColumnCount = headers.length;
    }
  }

  return {
    sections,
    totalRowCount,
    maxColumnCount,
  };
}


