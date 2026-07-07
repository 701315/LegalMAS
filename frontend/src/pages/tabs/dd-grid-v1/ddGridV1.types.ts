// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.types.ts
// Internal UI-типы для DD Grid V1.
//
// Правила:
// - никакой привязки к конкретным check_id / column_id / doc_type;
// - все идентификаторы, попадающие в UI-ключи (React key, ag-grid colId,
//   ag-grid rowId), — строятся детерминированно и уникально;
// - типы описывают view-модель, полученную из DDGridV1ResponseDTO
//   через селекторы ddGridV1.selectors.ts.
// =============================================================

import type {
  DDGridV1CellState,
  DDGridV1CellValueDTO,
  DDGridV1CheckDTO,
  DDGridV1ColumnDTO,
  DDGridV1ColumnFormat,
  DDGridV1DocTypeClassDTO,
  DDGridV1DocTypeDTO,
  DDGridV1DocumentMetaDTO,
  DDGridV1DrawerContentDTO,
  DDGridV1GlobalGroupDTO,
  DDGridV1LocationConfidence,
} from "../../../types/dealReview";

// -------------------------------------------------------------
// Runtime column identity
// -------------------------------------------------------------

/**
 * Scope, к которому относится runtime column.
 * - "global"  — колонка из global_groups (применима ко всем документам);
 * - "docType" — колонка из doc_type_classes (применима только к типам
 *   документов, перечисленным в applicableDocTypeCodes).
 */
export type DDGridV1ColumnScope = "global" | "docType";

/**
 * Одна runtime column в UI-модели.
 *
 * Универсальный принцип идентичности:
 *   runtimeColumnKey = scope|containerPath|checkId|columnId|indexInCheck
 *
 * Это единственный корректный ключ для UI, потому что column_id
 * может дублироваться внутри одного check-а (по контракту допустимо).
 */
export interface DDGridV1RuntimeColumn {
  /** Стабильный уникальный ключ этой колонки в UI. */
  runtimeKey: string;

  /** Scope этой колонки. */
  scope: DDGridV1ColumnScope;

  /**
   * Путь контейнера этой колонки в иерархии response:
   * - для global:  [globalGroupId]
   * - для docType: [docTypeClassId, typeCode]
   *
   * Используется только как строительный материал для runtimeKey
   * и для nested-header группировки; не парсится по частям в UI.
   */
  containerPath: string[];

  /**
   * Список type_code, к которым эта колонка применима.
   * Для global — пустой массив (применима ко всем).
   * Для docType — ровно один type_code (тот, в котором она объявлена).
   *
   * Правило not_applicable:
   * если applicableDocTypeCodes.length > 0 и docType документа
   * не входит в этот список — cell считается not_applicable.
   */
  applicableDocTypeCodes: string[];

  /** Идентификатор check-а, которому принадлежит колонка. */
  checkId: string;

  /** Индекс внутри массива check.columns (устраняет дубликаты column_id). */
  indexInCheck: number;

  /** Исходный column DTO (используется в форматтере и рендере ячейки). */
  column: DDGridV1ColumnDTO;
}

// -------------------------------------------------------------
// Hierarchy nodes (для nested headers ag-grid)
// -------------------------------------------------------------

/**
 * Узел иерархии заголовков верхнего уровня.
 *
 * Иерархия отражает структуру response:
 *   Global scope:
 *     GlobalGroup → Check → RuntimeColumn
 *   Doc-type scope:
 *     DocTypeClass → DocType → Check → RuntimeColumn
 *
 * ag-grid nested column groups строятся из этой структуры
 * без интерпретации бизнес-смысла.
 */
export interface DDGridV1CheckNode {
  /** Стабильный ключ для UI (уникален в масштабе всей иерархии). */
  nodeKey: string;

  checkId: string;
  checkName: string;
  displayOrder: number;

  /** Runtime-колонки этого check-а, отсортированные по display_order. */
  columns: DDGridV1RuntimeColumn[];

  /** Исходный check DTO (нужен для drawer / метаданных). */
  check: DDGridV1CheckDTO;
}

export interface DDGridV1DocTypeNode {
  nodeKey: string;

  typeCode: string;
  name: string;

  checks: DDGridV1CheckNode[];

  docType: DDGridV1DocTypeDTO;
}

export interface DDGridV1DocTypeClassNode {
  nodeKey: string;

  groupId: string;
  label: string;
  displayOrder: number;

  types: DDGridV1DocTypeNode[];

  docTypeClass: DDGridV1DocTypeClassDTO;
}

export interface DDGridV1GlobalGroupNode {
  nodeKey: string;

  groupId: string;
  label: string;
  displayOrder: number;

  checks: DDGridV1CheckNode[];

  globalGroup: DDGridV1GlobalGroupDTO;
}

// -------------------------------------------------------------
// Rows and cell views
// -------------------------------------------------------------

/**
 * Одна строка UI-матрицы = один документ из documents_meta.
 * Значения ячеек не встраиваются сюда — они разрешаются отдельно
 * через resolveCellView() для (row × runtimeColumn) пары.
 */
export interface DDGridV1MatrixRow {
  /** Стабильный row id для ag-grid и React. */
  rowId: string;

  documentId: string;
  filename: string;
  docType: string;
  status: string;
  folderPath: string | null;

  /** Исходный DTO (для drawer и служебных колонок). */
  meta: DDGridV1DocumentMetaDTO;
}

/**
 * Классификация доступности location для ячейки / поля.
 * Не хардкодит логику UI — только формально классифицирует контракт.
 */
export type DDGridV1LocationAvailability =
  | "exact"
  | "approximate"
  | "unavailable";

/**
 * View-модель одной ячейки для рендера.
 * Строится в UI-слое из (row, runtimeColumn, response) через resolveCellView().
 */
export interface DDGridV1CellView {
  /** Стабильный ключ ячейки. */
  cellKey: string;

  /** Финальное состояние ячейки (уже с учётом not_applicable/not_executed). */
  cellState: DDGridV1CellState;

  /** Готовая для рендера строка (уже пропущенная через форматтер). */
  displayText: string;

  /** Исходный формат колонки — для стилизации / доп. UI. */
  format: DDGridV1ColumnFormat;

  /** Классификация location (только для defined ячеек имеет смысл). */
  locationAvailability: DDGridV1LocationAvailability;

  /**
   * Исходный CellValueDTO, если он есть в response.
   * Может быть null для not_applicable / not_executed / error без DTO.
   */
  rawCell: DDGridV1CellValueDTO | null;

  /**
   * Уверенность location по контракту:
   * "high" | "low" | null.
   * Дублируется здесь для удобства UI, чтобы не разворачивать rawCell.
   */
  locationConfidence: DDGridV1LocationConfidence;
}

// -------------------------------------------------------------
// Aggregated derived model
// -------------------------------------------------------------

/**
 * Полная derived-модель DD Grid V1 для UI.
 *
 * Селектор строит эту модель один раз на response и мемоизируется
 * на уровне page component.
 */
export interface DDGridV1DerivedModel {
  dealId: string;
  runId: string;

  /** Иерархия global-заголовков (отсортированная). */
  globalGroups: DDGridV1GlobalGroupNode[];

  /** Иерархия doc-type заголовков (отсортированная). */
  docTypeClasses: DDGridV1DocTypeClassNode[];

  /** Плоский список всех runtime-колонок, в порядке появления в UI. */
  runtimeColumns: DDGridV1RuntimeColumn[];

  /** Быстрый lookup колонки по runtimeKey. */
  runtimeColumnsByKey: Record<string, DDGridV1RuntimeColumn>;

  /** Строки матрицы = документы. */
  rows: DDGridV1MatrixRow[];

  /** Быстрый lookup строки по documentId. */
  rowsByDocumentId: Record<string, DDGridV1MatrixRow>;

  /**
   * Быстрый lookup drawer-контента по (documentId, checkId).
   * Хранит ссылку на исходный DTO без интерпретации.
   */
  drawerContents: Record<string, Record<string, DDGridV1DrawerContentDTO>>;

  /** Cell values как в response, для быстрого lookup по (documentId, columnId). */
  cellValues: Record<string, Record<string, DDGridV1CellValueDTO>>;

  /** Сводная статистика для header. */
  stats: DDGridV1Stats;
}

/**
 * Универсальные stats для header без хардкода конкретных check-ов.
 * Определяются исключительно через cell_state и наличие drawer_content.
 */
export interface DDGridV1Stats {
  /** Количество документов в documents_meta. */
  documentsCount: number;

  /** Количество уникальных check-ов во всей иерархии. */
  checksCount: number;

  /** Количество runtime-колонок во всей иерархии. */
  runtimeColumnsCount: number;

  /**
   * Количество defined-ячеек по всей матрице
   * (по фактическим значениям в cell_values, без раздувания
   * пустыми not_applicable / not_executed).
   */
  definedCellsCount: number;

  /** Количество ячеек в состоянии not_defined. */
  notDefinedCellsCount: number;

  /** Количество ячеек в состоянии error. */
  errorCellsCount: number;
}


