// =============================================================
// src/utils/compositionHelpers.ts
// Единый helper-слой для работы с DocumentCompositionMeta.
//
// ПРАВИЛО: вся логика отображения composition/segment данных
// живёт только здесь. Ни DocumentTree, ни DocumentsTab,
// ни DDMatrixGrid не должны вычислять это самостоятельно.
// =============================================================

import type { DocumentCompositionMeta, DocumentColumnId, DocumentListItem } from "../types";

// -------------------------------------------------------------
// Базовые предикаты
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
  return doc.composition?.composition_type === "multi";
}

/**
 * Возвращает количество сегментов или null если данных нет.
 */
export function getSegmentCount(
  doc: DocumentListItem,
): number | null {
  const count = doc.composition?.segment_count;
  return typeof count === "number" ? count : null;
}

/**
 * Возвращает метку основного сегмента или null.
 * Пример: "Share Purchase Agreement", "Устав" и т.п.
 */
export function getPrimarySegmentLabel(
  doc: DocumentListItem,
): string | null {
  return doc.composition?.primary_segment_label ?? null;
}

/**
 * Является ли документ composite file (флаг из backend).
 * Возвращает false если данных нет.
 */
export function isCompositeFile(doc: DocumentListItem): boolean {
  return doc.composition?.is_composite_file === true;
}

// -------------------------------------------------------------
// Рендер-хелперы для таблицы (возвращают строку или число)
// Используются в DocumentsTab таблице и потенциально в экспорте.
// -------------------------------------------------------------

/**
 * Возвращает текстовое значение для ячейки таблицы документов
 * по ID composition-колонки.
 *
 * Возвращает строку или число — только примитивы,
 * чтобы функцию можно было использовать и в экспорте Excel/Word/PDF.
 */
export function getCompositionCellValue(
  colId: DocumentColumnId,
  doc: DocumentListItem,
): string | number {
  const meta = getCompositionMeta(doc);

  if (!meta) return "";

  switch (colId) {
    case "composition_type":
      return meta.composition_type === "multi" ? "Multi-document" : "Single";
    case "segment_count":
      return meta.segment_count ?? "";
    case "primary_segment_label":
      return meta.primary_segment_label ?? "";
    case "is_composite_file":
      return meta.is_composite_file ? "Да" : "Нет";
    default:
      return "";
  }
}

// -------------------------------------------------------------
// Badge-данные для UI (Tree, Grid и т.п.)
// Возвращают объекты описывающие что показать визуально,
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
 * Используй в DocumentTree, DDMatrixGrid и любых других местах
 * где нужно визуально показать composition-информацию.
 */
export function getCompositionBadgeData(
  doc: DocumentListItem,
): CompositionBadgeData {
  return getCompositionBadgeDataFromMeta(getCompositionMeta(doc));
}

// отдельная перегрузка для случаев где нет полного DocumentListItem
// (DDGrid, любой компонент с Map<docId, DocumentCompositionMeta>)

/**
 * Вычисляет badge-данные напрямую из DocumentCompositionMeta.
 * Используй когда нет полного DocumentListItem (например, в DDGrid).
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

  const segmentCount =
    typeof meta.segment_count === "number" ? meta.segment_count : 0;

  return {
    showMultiBadge: meta.composition_type === "multi",
    showSegmentCount: segmentCount > 1,
    segmentCount,
    showPrimaryLabel:
      meta.composition_type === "multi" &&
      typeof meta.primary_segment_label === "string" &&
      meta.primary_segment_label.length > 0,
    primaryLabel: meta.primary_segment_label ?? "",
    showCompositeBadge: meta.is_composite_file === true,
  };
}

