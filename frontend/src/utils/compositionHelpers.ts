// =============================================================
// src/utils/compositionHelpers.ts
// Единый helper-слой для работы с DocumentCompositionMeta.
//
// ПРАВИЛО: вся логика отображения composition/segment данных
// живёт только здесь. Ни DocumentTree, ни DocumentsTab,
// ни DDGrid, ни DDMatrixGrid не должны вычислять это самостоятельно.
// =============================================================

import type {
  DocumentCompositionMeta,
  DocumentColumnId,
  DocumentListItem,
} from "../types";

// -------------------------------------------------------------
// Универсальные adapter input shapes
// -------------------------------------------------------------

/**
 * Минимальный shape для row/view-моделей, у которых composition-данные
 * уже разложены по отдельным полям, а не лежат как composition: {...}.
 *
 * Используется для legacy/review grid row adapters.
 */
export interface CompositionMetaLike {
  compositionType?: "single" | "multi" | null;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;
  isCompositeFile?: boolean | null;
}

/**
 * Минимальный shape для review matrix row.
 * Нам не нужен импорт DTO-типа отсюда — helper остаётся слабо связанным
 * с feature-слоем и работает по structural typing.
 */
export interface ReviewCompositionMetaLike {
  isMultiDocument?: boolean | null;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;
  isCompositeFile?: boolean | null;
}

// -------------------------------------------------------------
// Базовые предикаты / adapters
// -------------------------------------------------------------

/**
 * Возвращает composition-метаданные документа или null если их нет.
 * Используй эту функцию везде вместо прямого обращения doc.composition.
 */
export function getCompositionMeta(
  doc: DocumentListItem,
): DocumentCompositionMeta | null {
  return doc.composition ?? null;
}

/**
 * Является ли документ multi-document файлом.
 * Возвращает false если данных нет.
 */
export function isMultiDocument(doc: DocumentListItem): boolean {
  return getCompositionMeta(doc)?.composition_type === "multi";
}

/**
 * Возвращает количество сегментов или 0 если данных нет.
 */
export function getSegmentCount(doc: DocumentListItem): number {
  const count = getCompositionMeta(doc)?.segment_count;
  return typeof count === "number" ? count : 0;
}

/**
 * Возвращает метку основного сегмента или null.
 * Пример: "Share Purchase Agreement", "Устав" и т.п.
 */
export function getPrimarySegmentLabel(doc: DocumentListItem): string | null {
  return getCompositionMeta(doc)?.primary_segment_label ?? null;
}

/**
 * Является ли документ composite file (флаг из backend).
 * Возвращает false если данных нет.
 */
export function isCompositeFile(doc: DocumentListItem): boolean {
  return getCompositionMeta(doc)?.is_composite_file === true;
}

/**
 * Явный adapter: DocumentListItem -> DocumentCompositionMeta | null
 * Нужен для единообразия API рядом с row-based adapters.
 */
export function toCompositionMetaFromDocument(
  doc: DocumentListItem,
): DocumentCompositionMeta | null {
  return getCompositionMeta(doc);
}

/**
 * Adapter для legacy matrix row / других row-моделей,
 * где composition уже разложен в плоские поля.
 */
export function toCompositionMetaFromLegacyMatrixRow(
  row: CompositionMetaLike | null | undefined,
): DocumentCompositionMeta | null {
  if (!row) return null;

  const hasAnyData =
    row.compositionType != null ||
    row.segmentCount != null ||
    row.primarySegmentLabel != null ||
    row.isCompositeFile != null;

  if (!hasAnyData) return null;

  return {
    composition_type: row.compositionType ?? "single",
    segment_count:
      typeof row.segmentCount === "number" ? row.segmentCount : 0,
    primary_segment_label: row.primarySegmentLabel ?? null,
    primary_segment_id: null,
    is_composite_file: row.isCompositeFile === true,
  };
}

/**
 * Adapter для review matrix row, где multi-document приходит как boolean.
 * Пока helper не зависит от конкретного DTO-типа и работает по shape.
 */
export function toCompositionMetaFromReviewMatrixRow(
  row: ReviewCompositionMetaLike | null | undefined,
): DocumentCompositionMeta | null {
  if (!row) return null;

  const hasAnyData =
    row.isMultiDocument != null ||
    row.segmentCount != null ||
    row.primarySegmentLabel != null ||
    row.isCompositeFile != null;

  if (!hasAnyData) return null;

  return {
    composition_type: row.isMultiDocument ? "multi" : "single",
    segment_count:
      typeof row.segmentCount === "number" ? row.segmentCount : 0,
    primary_segment_label: row.primarySegmentLabel ?? null,
    primary_segment_id: null,
    is_composite_file: row.isCompositeFile === true,
  };
}

// -------------------------------------------------------------
// Рендер-хелперы для таблицы (возвращают строку или число)
// Используются в DocumentsTab, Grid и потенциально в экспорте.
// -------------------------------------------------------------

/**
 * Возвращает текстовое значение для ячейки composition-колонки
 * напрямую из DocumentCompositionMeta.
 *
 * Возвращает строку или число — только примитивы,
 * чтобы функцию можно было использовать и в экспорте Excel/Word/PDF.
 */
export function getCompositionCellValueFromMeta(
  colId: DocumentColumnId,
  meta: DocumentCompositionMeta | null | undefined,
): string | number {
  if (!meta) return "";

  switch (colId) {
    case "composition_type":
      return meta.composition_type === "multi" ? "Multi-document" : "Single";
    case "segment_count":
      return meta.segment_count;
    case "primary_segment_label":
      return meta.primary_segment_label ?? "";
    case "is_composite_file":
      return meta.is_composite_file ? "Да" : "Нет";
    default:
      return "";
  }
}

/**
 * Backward-compatible helper для DocumentListItem.
 */
export function getCompositionCellValue(
  colId: DocumentColumnId,
  doc: DocumentListItem,
): string | number {
  return getCompositionCellValueFromMeta(colId, getCompositionMeta(doc));
}

// -------------------------------------------------------------
// Badge-данные для UI (Tree, Grid и т.п.)
// Возвращают объекты, описывающие что показать визуально,
// а не готовый JSX — чтобы не тащить React в utility-слой.
// -------------------------------------------------------------

/**
 * Данные для отображения composition-бейджей в строке документа.
 * Компонент сам решает как рендерить, helper только даёт данные.
 */
export interface CompositionBadgeData {
  /** Показывать ли бейдж "multi" */
  showMultiBadge: boolean;
  /** Показывать ли счётчик сегментов (только если > 1) */
  showSegmentCount: boolean;
  /** Число сегментов для отображения */
  segmentCount: number;
  /** Показывать ли метку основного сегмента */
  showPrimaryLabel: boolean;
  /** Текст метки основного сегмента */
  primaryLabel: string;
  /** Показывать ли "composite file" бейдж */
  showCompositeBadge: boolean;
}

/**
 * Вычисляет все данные для composition-бейджей одного документа.
 * Используй в DocumentTree, DocumentsTab и любых других местах,
 * где есть полный DocumentListItem.
 */
export function getCompositionBadgeData(
  doc: DocumentListItem,
): CompositionBadgeData {
  return getCompositionBadgeDataFromMeta(getCompositionMeta(doc));
}

/**
 * Вычисляет badge-данные напрямую из DocumentCompositionMeta.
 * Используй когда нет полного DocumentListItem (например, в DDGrid/DDMatrixGrid).
 */
export function getCompositionBadgeDataFromMeta(
  meta: DocumentCompositionMeta | null | undefined,
): CompositionBadgeData {
  if (!meta) {
    return {
      showMultiBadge: false,
      showSegmentCount: false,
      segmentCount: 0,
      showPrimaryLabel: false,
      primaryLabel: "",
      showCompositeBadge: false,
    };
  }

  const segmentCount = meta.segment_count;

  const primaryLabel =
    typeof meta.primary_segment_label === "string"
      ? meta.primary_segment_label.trim()
      : "";

  return {
    showMultiBadge: meta.composition_type === "multi",
    showSegmentCount: segmentCount > 1,
    segmentCount,
    showPrimaryLabel:
      meta.composition_type === "multi" && primaryLabel.length > 0,
    primaryLabel,
    showCompositeBadge: meta.is_composite_file === true,
  };
}

