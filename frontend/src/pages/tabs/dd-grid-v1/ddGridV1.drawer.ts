// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.drawer.ts
// Pure helpers для DD Grid V1 drawer.
//
// Правила:
// - никаких хардкодов конкретных check_id / column_id;
// - reason precedence реализован строго по контракту (только те поля,
//   которые сейчас гарантированы DTO). При расширении контракта
//   добавить следующие шаги (explanation, notes) — без переписывания UI;
// - функции чистые.
// =============================================================

import type {
  DDGridV1DrawerContentDTO,
  DDGridV1DrawerFieldDTO,
} from "../../../types/dealReview";

import {
  classifyDDGridV1LocationAvailability,
  formatDDGridV1CellText,
  getDDGridV1CellTone,
  type DDGridV1CellTone,
} from "./ddGridV1.formatters";

import type { DDGridV1LocationAvailability } from "./ddGridV1.types";

// -------------------------------------------------------------
// Reason precedence
// -------------------------------------------------------------

/**
 * Источник, из которого взят финальный reason.
 * Полезно для UI, чтобы, например, показывать label "показано на основании: display_text".
 */
export type DDGridV1ReasonSource =
  | "reason"
  | "review_message"
  | "display_text"
  | "none";

export interface DDGridV1ResolvedReason {
  text: string | null;
  source: DDGridV1ReasonSource;
}

function firstNonEmpty(...values: Array<string | null | undefined>): string | null {
  for (const v of values) {
    if (typeof v === "string" && v.trim().length > 0) {
      return v;
    }
  }
  return null;
}

/**
 * Возвращает финальный reason для drawer по precedence:
 *   1. drawer.reason
 *   2. drawer.review_message
 *   3. drawer.display_text
 *
 * ПРИМЕЧАНИЕ: контракт V1 сейчас не содержит metadata полей
 * "explanation" и "notes" на уровне DDGridV1DrawerContentDTO —
 * они, по документации, могут приходить внутри structured_data,
 * но во frontend-DTO не проброшены. При добавлении их в DTO —
 * вставить между шагами 1 и 2 без изменения UI.
 */
export function resolveDDGridV1DrawerReason(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1ResolvedReason {
  if (!drawer) return { text: null, source: "none" };

  const reason = firstNonEmpty(drawer.reason);
  if (reason) return { text: reason, source: "reason" };

  const reviewMessage = firstNonEmpty(drawer.review_message);
  if (reviewMessage) return { text: reviewMessage, source: "review_message" };

  const displayText = firstNonEmpty(drawer.display_text);
  if (displayText) return { text: displayText, source: "display_text" };

  return { text: null, source: "none" };
}

// -------------------------------------------------------------
// Field view model
// -------------------------------------------------------------

/**
 * View-модель одного поля внутри drawer.
 * Готова к прямому рендеру: строка, tone, availability.
 */
export interface DDGridV1DrawerFieldView {
  /** Стабильный ключ для React (учитывает индекс, т.к. column_id может дублироваться). */
  key: string;

  label: string;
  fieldName: string;
  columnId: string;

  cellState: DDGridV1DrawerFieldDTO["cell_state"];
  tone: DDGridV1CellTone;

  /** Готовый текст значения (уже отформатирован). */
  displayText: string;

  /** Классификация location строго по контракту. */
  locationAvailability: DDGridV1LocationAvailability;

  /** Исходный DTO (для перехода в viewer). */
  raw: DDGridV1DrawerFieldDTO;
}

/**
 * Строит view-модель списка полей drawer.
 * Для форматирования переиспользует formatDDGridV1CellText через
 * "виртуальную" column из полей DTO (label/format недоступны на уровне
 * DrawerField — используем text-режим как безопасный дефолт).
 *
 * ВАЖНО: DrawerFieldDTO не содержит format/enum_labels/unit/fallback_display —
 * это ограничение backend-контракта. Поэтому для drawer применяется
 * упрощённая форматизация: используем display_value при cell_state=defined,
 * fallback ("—" / "н/о" / "⚠ Ошибка") — иначе.
 * Никакой семантики "по имени поля" не читаем.
 */
export function buildDDGridV1DrawerFieldViews(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1DrawerFieldView[] {
  if (!drawer) return [];

  return (drawer.fields ?? []).map((field, index) => {
    const availability = classifyDDGridV1LocationAvailability({
      has_location_fallback: field.has_location_fallback,
      location_clause_ref: field.location_clause_ref,
      location_page: field.location_page,
      location_confidence: field.location_confidence,
    });

    // Используем формтатер в упрощённом режиме через synthetic column.
    // Это безопасно: formatDDGridV1CellText не читает бизнес-семантику,
    // а только применяет fallback-логику по cell_state.
    const syntheticColumn = {
      column_id: field.column_id,
      check_id: drawer.check_id,
      label: field.label,
      format: "text" as const,
      fallback_display: "—",
      display_order: 0,
      enum_labels: {},
      unit: null,
    };

    const displayText = formatDDGridV1CellText(
      field.cell_state,
      // resolve like defined cell if defined; иначе передаём null,
      // чтобы formatter выдал fallback по своей логике
      field.cell_state === "defined"
        ? {
            cell_state: field.cell_state,
            display_value: field.display_value,
            raw_value: field.raw_value,
            location_clause_ref: field.location_clause_ref,
            location_page: field.location_page,
            location_confidence: field.location_confidence,
            has_location_fallback: field.has_location_fallback,
            location_fallback_reason: field.location_fallback_reason,
          }
        : null,
      syntheticColumn,
    );

    return {
      key: `${field.column_id}#${index}`,
      label: field.label,
      fieldName: field.field_name,
      columnId: field.column_id,
      cellState: field.cell_state,
      tone: getDDGridV1CellTone(field.cell_state),
      displayText,
      locationAvailability: availability,
      raw: field,
    };
  });
}

// -------------------------------------------------------------
// Evidence
// -------------------------------------------------------------

/**
 * Возвращает нормализованный список evidence items:
 * убирает пустые строки, обрезает пробелы, сохраняет порядок.
 */
export function normalizeDDGridV1EvidenceItems(
  drawer: DDGridV1DrawerContentDTO | null,
): string[] {
  if (!drawer) return [];
  const items = drawer.evidence_items ?? [];
  const out: string[] = [];
  for (const item of items) {
    if (typeof item === "string" && item.trim().length > 0) {
      out.push(item.trim());
    }
  }
  return out;
}


