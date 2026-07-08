// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.exportBuilder.ts
// Единый source of truth для экспорта DD Grid V1.
//
// Правила:
// - экспорт всегда идентичен тому, что видит юрист на экране;
// - список колонок = базовые + выбранные extra columns;
// - фильтры применяются те же (visibleCheckIds, includePassResults);
// - никаких хардкодов бизнес-логики.
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
// Review status labels (дублируем логику из DDGridV1List)
// -------------------------------------------------------------

function getReviewStatusLabel(status: string | null | undefined): string {
  if (!status || typeof status !== "string" || status.trim().length === 0) {
    return "—";
  }
  const normalized = status.trim();
  switch (normalized) {
    case "needs_review":
      return "Требует внимания юриста";
    case "no_issue_detected":
    case "ok":
      return "Без замечаний";
    case "not_applicable":
      return "Неприменимо";
    case "unclear":
      return "Результат не определён";
    default:
      return normalized;
  }
}

// -------------------------------------------------------------
// Location text (дублируем логику из DDGridV1List)
// -------------------------------------------------------------

function buildLocationText(drawer: DDGridV1DrawerContentDTO | null): string {
  if (!drawer) return "";

  for (const field of drawer.fields ?? []) {
    const parts: string[] = [];
    if (typeof field.location_page === "number") {
      parts.push(`стр. ${field.location_page}`);
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
// Column definitions
// -------------------------------------------------------------

/**
 * Базовые колонки — всегда экспортируются.
 * Порядок совпадает с UI.
 *
 * Колонка "№" — сквозная нумерация записей в экспорте.
 * Индекс подставляется в buildDDGridV1ExportTable, а не в extract,
 * потому что extract работает с одной row без знания её позиции.
 */
const BASE_EXPORT_COLUMNS: readonly DDGridV1ExportColumn[] = [
  {
    id: "rowNumber",
    label: "№",
    extract: () => "", // подставляется отдельно в buildDDGridV1ExportTable
  },
  {
    id: "documentName",
    label: "Документ",
    extract: (r) => r.documentName,
  },
  {
    id: "docType",
    label: "Тип документа",
    extract: (r) => r.docType,
  },
  {
    id: "checkName",
    label: "Проверка",
    extract: (r) => r.checkName,
  },
  {
    id: "displayText",
    label: "Результат",
    extract: (r) => r.displayText,
  },
  {
    id: "reviewStatus",
    label: "Статус",
    extract: (r) => r.reviewStatusLabel,
  },
  {
    id: "locationText",
    label: "Локация",
    extract: (r) => r.locationText,
  },
] as const;

/**
 * Extra колонки — включаются, если выбраны в UI.
 * ID должны совпадать с DD_GRID_V1_EXTRA_COLUMNS.id из DDGridV1List.
 */
const EXTRA_EXPORT_COLUMNS: Record<string, DDGridV1ExportColumn> = {
  detectionLevel: {
    id: "detectionLevel",
    label: "Метод анализа",
    extract: (r) => r.detectionLevel,
  },
  qcStatus: {
    id: "qcStatus",
    label: "QC",
    extract: (r) => r.qcStatus,
  },
  confidence: {
    id: "confidence",
    label: "Уверенность",
    extract: (r) => r.confidenceFormatted,
  },
  qualityFlags: {
    id: "qualityFlags",
    label: "Предупреждения",
    extract: (r) => r.qualityFlagsText,
  },
  agentName: {
    id: "agentName",
    label: "Агент",
    extract: (r) => r.agentName,
  },
  modelVersion: {
    id: "modelVersion",
    label: "Модель",
    extract: (r) => r.modelVersion,
  },
  executionTime: {
    id: "executionTime",
    label: "Время выполнения",
    extract: (r) => r.executionTime,
  },
  retryAttempts: {
    id: "retryAttempts",
    label: "Попытки LLM",
    extract: (r) => r.retryAttempts,
  },
  inputTokens: {
    id: "inputTokens",
    label: "Input tokens",
    extract: (r) => r.inputTokens,
  },
  outputTokens: {
    id: "outputTokens",
    label: "Output tokens",
    extract: (r) => r.outputTokens,
  },
};

/**
 * Порядок extra колонок при экспорте.
 * Совпадает с DD_GRID_V1_EXTRA_COLUMNS в DDGridV1List.
 */
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
): DDGridV1ExportColumn[] {
  const columns: DDGridV1ExportColumn[] = [...BASE_EXPORT_COLUMNS];

  const visibleExtras = new Set(visibleExtraColumnIds ?? []);
  if (visibleExtras.size === 0) return columns;

  for (const id of EXTRA_EXPORT_COLUMN_ORDER) {
    if (!visibleExtras.has(id)) continue;
    const col = EXTRA_EXPORT_COLUMNS[id];
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
}): DDGridV1ExportSourceRow[] {
  const { model, visibleCheckIds, includePassResults = true } = params;

  // Собираем все check nodes (deduplicated)
  const allChecks: DDGridV1CheckNode[] = [];
  const seenCheckIds = new Set<string>();

  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      if (!seenCheckIds.has(check.checkId)) {
        seenCheckIds.add(check.checkId);
        allChecks.push(check);
      }
    }
  }
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
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

      const drawer =
        model.drawerContents[v1Row.documentId]?.[check.checkId] ?? null;
      if (!drawer) continue;

      // pass фильтр
      if (
        !includePassResults &&
        (drawer.review_status === "no_issue_detected" ||
          drawer.review_status === "ok")
      ) {
        continue;
      }

      result.push(buildExportSourceRow(v1Row, check, drawer));
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
): DDGridV1ExportSourceRow {
  const detectionLevelInfo = resolveDDGridV1DetectionLevel(drawer);
  const confidenceInfo = resolveDDGridV1Confidence(drawer);
  const qualityFlags = resolveDDGridV1QualityFlags(drawer);
  const qcAuditInfo = resolveDDGridV1QcAuditInfo(drawer);
  const observability = resolveDDGridV1Observability(drawer);

  const qcStatusLabel =
    qcAuditInfo.status && qcAuditInfo.status !== "pending"
      ? {
          approved: "Одобрено",
          rejected: "Отклонено",
          needs_review: "Нужна проверка",
        }[qcAuditInfo.status] ?? qcAuditInfo.status
      : "";

  return {
    documentName: v1Row.filename || "[no name]",
    docType: v1Row.docType || "—",
    checkName: check.checkName || check.checkId,
    displayText: drawer.display_text?.trim() || "",
    reviewStatusLabel: getReviewStatusLabel(drawer.review_status),
    locationText: buildLocationText(drawer),

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
 *
 * headerRows содержит 3 строки:
 *   Row 0: Scope groups (например, "Confidentiality", "Governing Law")
 *   Row 1: Check names (например, "Конфиденциальность и коммерческая тайна")
 *   Row 2: Runtime column labels (например, "Confidentiality status")
 *
 * pinnedHeaders — заголовки для первых pinnedColumnCount колонок,
 * которые объединяются по вертикали через все 3 строки.
 * Обычно это ["№", "Документ", "Тип документа"].
 */
export interface DDGridV1MatrixExportTable {
  /** Заголовки первых pinned колонок (merged vertically). */
  pinnedHeaders: string[];
  /** Три строки заголовков для остальных колонок. */
  headerRows: [
    DDGridV1MatrixHeaderCell[],
    DDGridV1MatrixHeaderCell[],
    DDGridV1MatrixHeaderCell[],
  ];
  /** Полный плоский список column labels на самом нижнем уровне (для fallback). */
  leafHeaders: string[];
  /** Data rows: первые pinnedColumnCount = pinned, остальные — data columns. */
  rows: string[][];
  /** Количество pinned колонок (для расчёта colSpan для pinned headers). */
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
}): DDGridV1ExportTable {
  const columns = buildDDGridV1ExportColumns(params.visibleExtraColumnIds);
  const sourceRows = buildDDGridV1ExportRows({
    model: params.model,
    visibleCheckIds: params.visibleCheckIds,
    includePassResults: params.includePassResults,
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

/**
 * Backward-compatible alias. Существующий код может импортировать
 * старое имя buildDDGridV1ExportTable — оно продолжает работать
 * как list export.
 */
export const buildDDGridV1ExportTable = buildDDGridV1ListExportTable;

/**
 * Строит matrix export — двумерная таблица с иерархическими заголовками.
 *
 * Структура (Вариант 2 — 3 уровня без top-level):
 *   pinned headers: № | Документ | Тип документа (merged vertically)
 *   Row 0 (scope group):    | Confidentiality (colSpan=3) | Governing Law (colSpan=2) | ...
 *   Row 1 (check name):     | Конф. и ком. тайна (colSpan=3) | Прим. право (colSpan=2) | ...
 *   Row 2 (runtime column): | Status | Term regime | Term value | Applicable | Forum | ...
 *
 * Data rows: rows = [[№, Документ, Тип, cell1, cell2, ...]]
 */
export function buildDDGridV1MatrixExportTable(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
}): DDGridV1MatrixExportTable {
  const { model, visibleCheckIds } = params;
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
    if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) return;
    if (seenCheckIds.has(check.checkId)) return;
    seenCheckIds.add(check.checkId);

    const checkName = check.checkName || check.checkId;

    for (const runtimeColumn of check.columns) {
      const columnLabel = runtimeColumn.column.label;

      matrixColumns.push({
        scopeGroupLabel,
        checkName,
        columnLabel,
        extract: (row) => {
          const perDoc = model.cellValues[row.documentId];
          const rawCell = perDoc
            ? perDoc[runtimeColumn.column.column_id] ?? null
            : null;

          if (!rawCell) {
            if (
              runtimeColumn.applicableDocTypeCodes.length > 0 &&
              !runtimeColumn.applicableDocTypeCodes.includes(row.docType)
            ) {
              return "н/о";
            }
            return "—";
          }

          if (rawCell.cell_state === "not_applicable") return "н/о";
          if (rawCell.cell_state === "error") return "⚠ Ошибка";
          if (rawCell.cell_state === "not_defined") return "—";
          if (rawCell.cell_state === "not_executed") return "—";

          return rawCell.display_value || "";
        },
      });
    }
  };

  // Global groups: scope label = group.label
  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      processCheck(check, group.label);
    }
  }

  // Doc-type classes: scope label = "{class.label} · {type.name}"
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      const scopeLabel = `${cls.label} · ${t.name}`;
      for (const check of t.checks) {
        processCheck(check, scopeLabel);
      }
    }
  }

  // ── Строим 3 строки заголовков с colSpan ────────────────────
  // Row 0: scope groups. Соседние колонки с одинаковым scopeGroupLabel мержатся.
  // Row 1: check names. Соседние колонки с одинаковым (scope + check) мержатся.
  // Row 2: runtime column labels (всегда colSpan=1).

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
  // На check row нам нужны фактические label, а не composite key.
  // Пересобираем check row с правильными labels, сохраняя структуру colSpan.
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

  // ── Data rows ──────────────────────────────────────────────
  const pinnedHeaders = ["№", "Документ", "Тип документа"];
  const pinnedColumnCount = pinnedHeaders.length;

  const rows: string[][] = model.rows.map((row, index) => {
    const rowValues: string[] = [
      String(index + 1),
      row.filename || "[no name]",
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

/**
 * Один section в структурированном экспорте.
 * Каждая section — независимая таблица с заголовком.
 * Используется для Layout 2 (section per document)
 * и Layout 3 (section per scope group).
 */
export interface DDGridV1ExportSection {
  /** Заголовок секции (например, "Simonova_SPA_Real_Estate.DOCX" или "Confidentiality"). */
  title: string;
  /** Опциональный подзаголовок (например, "contract_1.6_real_estate"). */
  subtitle?: string;
  /** Заголовки колонок этой секции. */
  headers: string[];
  /** Данные секции. */
  rows: string[][];
}

/**
 * Result type для sectioned export.
 * Порядок sections — тот же, что порядок появления в UI.
 */
export interface DDGridV1SectionedExportTable {
  sections: DDGridV1ExportSection[];
  /** Общее количество rows во всех sections. */
  totalRowCount: number;
  /** Максимальное количество колонок в любой секции. */
  maxColumnCount: number;
}

// -------------------------------------------------------------
// Layout 2 — Section per document (row grouping)
// -------------------------------------------------------------

/**
 * Строит sectioned export: одна секция на документ.
 *
 * Структура каждой секции:
 *   Title: filename документа
 *   Subtitle: doc_type
 *   Table:
 *     | Проверка | Параметр | Значение |
 *     | ...      | ...      | ...      |
 *
 * Стратегическое преимущество:
 * - каждая таблица узкая (3 колонки) — идеально влезает в PDF/Word portrait или landscape
 * - юрист видит все проверки одного документа в одном месте
 * - естественно для юридического DD memo формата
 */
export function buildDDGridV1DocumentSectionedExportTable(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
}): DDGridV1SectionedExportTable {
  const { model, visibleCheckIds } = params;
  const visibleCheckSet = visibleCheckIds ? new Set(visibleCheckIds) : null;

  // Собираем deduplicated check nodes с их scope group для контекста.
  interface CheckWithScope {
    check: DDGridV1CheckNode;
    scopeGroupLabel: string;
  }

  const allChecks: CheckWithScope[] = [];
  const seenCheckIds = new Set<string>();

  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) continue;
      if (seenCheckIds.has(check.checkId)) continue;
      seenCheckIds.add(check.checkId);
      allChecks.push({ check, scopeGroupLabel: group.label });
    }
  }
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) continue;
        if (seenCheckIds.has(check.checkId)) continue;
        seenCheckIds.add(check.checkId);
        allChecks.push({
          check,
          scopeGroupLabel: `${cls.label} · ${t.name}`,
        });
      }
    }
  }

  const sections: DDGridV1ExportSection[] = [];
  let totalRowCount = 0;

  for (const v1Row of model.rows) {
    const rows: string[][] = [];

    for (const { check, scopeGroupLabel } of allChecks) {
      const drawer =
        model.drawerContents[v1Row.documentId]?.[check.checkId] ?? null;
      if (!drawer) continue;

      // Одна check = группа строк (одна на runtime column)
      const checkName = check.checkName || check.checkId;

      for (const runtimeColumn of check.columns) {
        const perDoc = model.cellValues[v1Row.documentId];
        const rawCell = perDoc
          ? perDoc[runtimeColumn.column.column_id] ?? null
          : null;

        let value = "";
        if (!rawCell) {
          if (
            runtimeColumn.applicableDocTypeCodes.length > 0 &&
            !runtimeColumn.applicableDocTypeCodes.includes(v1Row.docType)
          ) {
            value = "н/о";
          } else {
            value = "—";
          }
        } else {
          switch (rawCell.cell_state) {
            case "not_applicable":
              value = "н/о";
              break;
            case "error":
              value = "⚠ Ошибка";
              break;
            case "not_defined":
            case "not_executed":
              value = "—";
              break;
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
      title: v1Row.filename || "[no name]",
      subtitle: v1Row.docType || undefined,
      headers: ["Проверка", "Параметр", "Значение"],
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

// -------------------------------------------------------------
// Layout 3 — Section per scope group
// -------------------------------------------------------------

/**
 * Строит sectioned export: одна секция на scope group.
 *
 * Структура каждой секции:
 *   Title: "Confidentiality" / "Governing Law" / "Договор купли-продажи недвижимости"
 *   Table:
 *     | № | Документ | Тип | Runtime col 1 | Runtime col 2 | ... |
 *
 * Стратегическое преимущество:
 * - каждая таблица узкая — влезает в landscape A4
 * - позволяет сравнить одну группу проверок между документами
 * - идеально для тематических compliance reports
 */
export function buildDDGridV1ScopeGroupSectionedExportTable(params: {
  model: DDGridV1DerivedModel;
  visibleCheckIds?: readonly string[];
}): DDGridV1SectionedExportTable {
  const { model, visibleCheckIds } = params;
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
      const perDoc = model.cellValues[row.documentId];
      const rawCell = perDoc
        ? perDoc[runtimeColumn.column.column_id] ?? null
        : null;

      if (!rawCell) {
        if (
          runtimeColumn.applicableDocTypeCodes.length > 0 &&
          !runtimeColumn.applicableDocTypeCodes.includes(row.docType)
        ) {
          return "н/о";
        }
        return "—";
      }
      switch (rawCell.cell_state) {
        case "not_applicable":
          return "н/о";
        case "error":
          return "⚠ Ошибка";
        case "not_defined":
        case "not_executed":
          return "—";
        default:
          return rawCell.display_value || "";
      }
    };
  };

  const processCheck = (
    check: DDGridV1CheckNode,
    sectionPlan: ScopeSectionPlan,
  ) => {
    if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) return;
    if (seenCheckIds.has(check.checkId)) return;
    seenCheckIds.add(check.checkId);

    const checkName = check.checkName || check.checkId;

    for (const runtimeColumn of check.columns) {
      sectionPlan.columns.push({
        checkName,
        columnLabel: runtimeColumn.column.label,
        extract: makeExtract(runtimeColumn),
      });
    }
  };

  // Global scope groups
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

  // Doc-type scope groups: одна секция на (class · type)
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      const plan: ScopeSectionPlan = {
        title: cls.label,
        subtitle: t.name,
        columns: [],
      };
      for (const check of t.checks) {
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
    // Строим headers: № | Документ | Тип | {check} — {column} × N
    const headers = [
      "№",
      "Документ",
      "Тип документа",
      ...plan.columns.map((c) => `${c.checkName} — ${c.columnLabel}`),
    ];

    const rows: string[][] = model.rows.map((row, index) => {
      const values: string[] = [
        String(index + 1),
        row.filename || "[no name]",
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


