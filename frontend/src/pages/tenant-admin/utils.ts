// =============================================================
// src/pages/tenant-admin/utils.ts
//
// Pure utility функции для страницы TenantAdmin: форматирование
// дат, чисел, длительностей, нормализация уровней логов, mapping
// tone → CSS class.
//
// Дизайн-принцип: все функции здесь — pure (без side effects,
// без React state). Это делает их тривиально тестируемыми и
// переиспользуемыми в любых компонентах внутри admin panel.
// =============================================================

import { PROJECT_ROLE_LABELS } from "./constants";

// ─── Date Formatting ─────────────────────────────────────────────────────

/**
 * Форматирует ISO datetime string в русскую локализованную строку
 * с датой и временем.
 *
 * @example
 * formatDateTime("2026-08-08T15:30:00Z") // "08.08.2026, 18:30"
 * formatDateTime(null) // "—"
 * formatDateTime("invalid") // "—"
 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Форматирует ISO datetime string в русскую локализованную дату
 * без времени, с полным названием месяца.
 *
 * @example
 * formatDate("2026-08-08T15:30:00Z") // "8 августа 2026 г."
 * formatDate(null) // "—"
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

// ─── Number Formatting ───────────────────────────────────────────────────

/**
 * Форматирует число с русскими разделителями тысяч.
 *
 * @example
 * fmt(1234567) // "1 234 567"
 * fmt(0) // "0"
 * fmt(null) // "—"
 */
export function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("ru-RU").format(value);
}

/**
 * Форматирует миллисекунды с суффиксом "мс".
 * Для значений < 10 показывает 2 знака после запятой.
 * Для значений < 1 показывает "< 1 мс".
 *
 * @example
 * fmtMs(1234) // "1 234 мс"
 * fmtMs(5.678) // "5.68 мс"
 * fmtMs(0.5) // "< 1 мс"
 */
export function fmtMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (value < 1) return "< 1 мс";
  return `${new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: value < 10 ? 2 : 0,
  }).format(value)} мс`;
}

/**
 * Форматирует длительность в секундах.
 * Для значений < 60 сек показывает секунды с 1 знаком после запятой.
 * Для больших значений разбивает на минуты и секунды.
 *
 * @example
 * fmtDurationSeconds(45.5) // "45.5 с"
 * fmtDurationSeconds(125) // "2 мин 5 с"
 */
export function fmtDurationSeconds(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return "—";
  if (sec < 60) return `${sec.toFixed(1)} с`;
  const mins = Math.floor(sec / 60);
  const rest = Math.round(sec - mins * 60);
  return `${mins} мин ${rest} с`;
}

// ─── Log Level Normalization ─────────────────────────────────────────────

/**
 * Нормализует уровень лога к каноническому виду.
 * Обрабатывает алиас "warn" → "warning".
 * Fallback на "info" если значение отсутствует.
 *
 * @example
 * normLevel("ERROR") // "error"
 * normLevel("warn") // "warning"
 * normLevel(null) // "info"
 */
export function normLevel(level: string | null | undefined): string {
  if (!level) return "info";
  const n = level.toLowerCase();
  return n === "warn" ? "warning" : n;
}

// ─── Tone → CSS Class Mapping ────────────────────────────────────────────

/**
 * Возвращает Tailwind class для текста в зависимости от semantic tone.
 * Используется в KpiCard, ProjectRow, RunStatusCell и других местах где
 * нужно семантически окрасить значение.
 *
 * @example
 * <p className={toneClass("error")}>...</p> // text-[var(--color-error-text)]
 */
export function toneClass(
  tone: "ok" | "warn" | "error" | "default" | "neutral",
): string {
  if (tone === "ok") return "text-[var(--color-success-text)]";
  if (tone === "warn") return "text-[var(--color-warning-text)]";
  if (tone === "error") return "text-[var(--color-error-text)]";
  return "text-[var(--text-primary)]";
}

// ─── Role Label Helpers ──────────────────────────────────────────────────

/**
 * Возвращает человекочитаемое название project-level роли.
 * Fallback на raw role code если ключ не найден в PROJECT_ROLE_LABELS.
 *
 * @example
 * projectRoleLabel("admin") // "Администратор"
 * projectRoleLabel("custom_role") // "custom_role"
 */
export function projectRoleLabel(role: string): string {
  return PROJECT_ROLE_LABELS[role.toLowerCase()] ?? role;
}


