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
  DDGridV1DetectionLevel,
  DDGridV1DrawerContentDTO,
  DDGridV1DrawerFieldDTO,
  DDGridV1DrawerQcStatus,
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

// -------------------------------------------------------------
// Detection level
// -------------------------------------------------------------

export interface DDGridV1DetectionLevelInfo {
  level: DDGridV1DetectionLevel | null;
  /** Короткий label для badge: "L1", "L2", "L3", "L4" или null. */
  badge: string | null;
  /** Человекочитаемое описание. */
  label: string;
}

const DETECTION_LEVEL_LABELS: Record<DDGridV1DetectionLevel, string> = {
  L1: "Паттерн",
  L2: "LLM",
  L3: "RAG + LLM",
  L4: "Ручная проверка",
};

/**
 * Строит info-объект detection level для рендера.
 * Возвращает null-safe структуру — всегда безопасно вызывать.
 */
export function resolveDDGridV1DetectionLevel(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1DetectionLevelInfo {
  const level = drawer?.detection_level ?? null;
  if (!level) {
    return { level: null, badge: null, label: "Не определён" };
  }
  return {
    level,
    badge: level,
    label: DETECTION_LEVEL_LABELS[level] ?? level,
  };
}

// -------------------------------------------------------------
// Confidence
// -------------------------------------------------------------

export type DDGridV1ConfidenceTier = "high" | "medium" | "low";

export interface DDGridV1ConfidenceInfo {
  value: number | null;
  /** Tier для цветового кодирования. */
  tier: DDGridV1ConfidenceTier | null;
  /** Форматированная строка для рендера, например "0.87". */
  formatted: string | null;
}

/**
 * Строит info-объект confidence для рендера.
 * Tier:
 *   >= 0.80 → "high"  (зелёный)
 *   >= 0.60 → "medium" (жёлтый)
 *   <  0.60 → "low"   (красный)
 */
export function resolveDDGridV1Confidence(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1ConfidenceInfo {
  const value = drawer?.confidence ?? null;
  if (value === null || typeof value !== "number") {
    return { value: null, tier: null, formatted: null };
  }

  const tier: DDGridV1ConfidenceTier =
    value >= 0.8 ? "high" : value >= 0.6 ? "medium" : "low";

  return {
    value,
    tier,
    formatted: value.toFixed(2),
  };
}

// -------------------------------------------------------------
// Quality flags
// -------------------------------------------------------------

const QUALITY_FLAG_LABELS: Record<string, string> = {
  structure_degraded: "Структура нарушена",
  llm_fallback_used: "Fallback модель",
  retry_used: "Повторная попытка",
  partial_result: "Частичный результат",
  confidence_below_threshold: "Низкая уверенность",
  missing_provenance: "Нет провенанса",
};

export interface DDGridV1QualityFlagItem {
  key: string;
  label: string;
}

/**
 * Возвращает нормализованный список quality flags для рендера.
 * Только true-ключи (по контракту backend хранит только true).
 * Для известных ключей — локализованный label.
 * Для неизвестных — raw key с форматированием.
 */
export function resolveDDGridV1QualityFlags(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1QualityFlagItem[] {
  const flags = drawer?.quality_flags;
  if (!flags || typeof flags !== "object") return [];

  return Object.keys(flags).map((key) => ({
    key,
    label: QUALITY_FLAG_LABELS[key] ?? key.replace(/_/g, " "),
  }));
}

// -------------------------------------------------------------
// QC Audit Trail
// -------------------------------------------------------------

export interface DDGridV1QcAuditInfo {
  status: DDGridV1DrawerQcStatus | null;
  /** Значение для select при редактировании. */
  editableStatus: DDGridV1DrawerQcStatus;
  by: string | null;
  at: string | null;
  /** Форматированная дата для рендера. */
  atFormatted: string | null;
  comment: string | null;
  /** True если QC уже проводился (status != pending и != null). */
  hasBeenActioned: boolean;
}

function formatISODate(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/**
 * Строит info-объект QC audit trail из drawer content.
 * Не требует пропсов от родителя — все данные берёт из drawer.
 */
export function resolveDDGridV1QcAuditInfo(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1QcAuditInfo {
  const status = drawer?.qc_status ?? null;
  const editableStatus: DDGridV1DrawerQcStatus = status ?? "pending";

  return {
    status,
    editableStatus,
    by: drawer?.qc_by ?? null,
    at: drawer?.qc_at ?? null,
    atFormatted: formatISODate(drawer?.qc_at ?? null),
    comment: drawer?.qc_comment ?? null,
    hasBeenActioned: !!status && status !== "pending",
  };
}

// -------------------------------------------------------------
// Observability
// -------------------------------------------------------------

export interface DDGridV1ObservabilityInfo {
  agentName: string | null;
  modelVersion: string | null;
  executionTimeMs: number | null;
  /** Форматированная строка, например "1 840 ms" или null. */
  executionTimeFormatted: string | null;
  retryAttempts: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  /** True если есть хотя бы одно непустое поле. */
  hasAnyData: boolean;
}

function formatMs(ms: number | null): string | null {
  if (ms === null || ms === undefined) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * Строит info-объект observability из drawer content.
 */
export function resolveDDGridV1Observability(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1ObservabilityInfo {
  const agentName = drawer?.agent_name ?? null;
  const modelVersion = drawer?.model_version ?? null;
  const executionTimeMs = drawer?.execution_time_ms ?? null;
  const retryAttempts = drawer?.retry_attempts ?? null;
  const inputTokens = drawer?.input_tokens ?? null;
  const outputTokens = drawer?.output_tokens ?? null;

  const hasAnyData =
    !!agentName ||
    !!modelVersion ||
    executionTimeMs !== null ||
    retryAttempts !== null ||
    inputTokens !== null ||
    outputTokens !== null;

  return {
    agentName,
    modelVersion,
    executionTimeMs,
    executionTimeFormatted: formatMs(executionTimeMs),
    retryAttempts,
    inputTokens,
    outputTokens,
    hasAnyData,
  };
}

