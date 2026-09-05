// =============================================================
// src/pages/tenant-admin/utils.ts
//
// Pure utility functions for the TenantAdmin dashboard: formatting
// dates, numbers, durations, normalizing log levels, and mapping
// semantic tones to CSS classes.
//
// Design principle: All functions here are pure (no side effects,
// no React state). This makes them easily testable and reusable
// across any component in the admin panel.
// =============================================================

import { PROJECT_ROLE_LABELS } from "./constants";

export type TranslationFn = (key: string, options?: any) => string;

// ─── Date Formatting ─────────────────────────────────────────────────────

/**
 * Formats an ISO datetime string into a localized date and time string.
 * Defaults to canonical "en-US" locale.
 *
 * @example
 * formatDateTime("2026-08-08T15:30:00Z", "en-US") // "08/08/2026, 03:30 PM"
 * formatDateTime(null) // "—"
 * formatDateTime("invalid") // "—"
 */
export function formatDateTime(
  iso: string | null | undefined,
  locale: string = "en-US",
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Formats an ISO datetime string into a localized date without time,
 * displaying the full month name.
 *
 * @example
 * formatDate("2026-08-08T15:30:00Z", "en-US") // "August 08, 2026"
 * formatDate(null) // "—"
 */
export function formatDate(
  iso: string | null | undefined,
  locale: string = "en-US",
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale, {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

// ─── Number Formatting ───────────────────────────────────────────────────

/**
 * Formats a number with thousands separators according to the locale.
 *
 * @example
 * fmt(1234567, "en-US") // "1,234,567"
 * fmt(0) // "0"
 * fmt(null) // "—"
 */
export function fmt(
  value: number | null | undefined,
  locale: string = "en-US",
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(locale).format(value);
}

/**
 * Formats milliseconds with localized unit suffix.
 * For values < 10, displays up to 2 decimal digits.
 * For values < 1, utilizes localized short boundary template.
 *
 * @example
 * fmtMs(1234, "en-US", t) // "1,234 ms"
 * fmtMs(5.678, "en-US", t) // "5.68 ms"
 * fmtMs(0.5, "en-US", t) // "< 1 ms"
 */
export function fmtMs(
  value: number | null | undefined,
  locale: string = "en-US",
  t?: TranslationFn,
): string {
  if (value == null || Number.isNaN(value)) return "—";

  if (value < 1) {
    return t ? t("units.msShortLessThanOne") : "< 1 ms";
  }

  const formatted = new Intl.NumberFormat(locale, {
    maximumFractionDigits: value < 10 ? 2 : 0,
  }).format(value);

  const suffix = t ? t("units.ms") : "ms";
  return `${formatted} ${suffix}`;
}

/**
 * Formats a duration in seconds with locale awareness.
 * For values < 60 sec, displays seconds with 1 decimal place.
 * For larger values, breaks down into minutes and seconds.
 *
 * @example
 * fmtDurationSeconds(45.5, "en-US", t) // "45.5 s"
 * fmtDurationSeconds(125, "en-US", t) // "2 min 5 s"
 */
export function fmtDurationSeconds(
  sec: number | null | undefined,
  locale: string = "en-US",
  t?: TranslationFn,
): string {
  if (sec == null || Number.isNaN(sec)) return "—";

  const sSuffix = t ? t("units.s") : "s";
  const minSuffix = t ? t("units.min") : "min";

  if (sec < 60) {
    const formattedSec = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(sec);
    return `${formattedSec} ${sSuffix}`;
  }

  const mins = Math.floor(sec / 60);
  const rest = Math.round(sec - mins * 60);

  const formattedMins = new Intl.NumberFormat(locale).format(mins);
  const formattedRest = new Intl.NumberFormat(locale).format(rest);

  return `${formattedMins} ${minSuffix} ${formattedRest} ${sSuffix}`;
}

// ─── Log Level Normalization ─────────────────────────────────────────────

/**
 * Normalizes log level to canonical lowercase format.
 * Handles alias "warn" → "warning".
 * Defaults to "info" if missing.
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
 * Returns Tailwind class for text depending on semantic tone.
 * Used in KpiCard, ProjectRow, RunStatusCell and other components
 * requiring semantic color formatting.
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
 * Returns human-readable label for a project-level role.
 * Supports i18n via translation function. Falls back to legacy
 * constants or raw role code if translation key is missing.
 *
 * @example
 * projectRoleLabel("admin", t) // "Administrator"
 * projectRoleLabel("custom_role") // "custom_role"
 */
export function projectRoleLabel(role: string, t?: TranslationFn): string {
  const normalizedRole = role.toLowerCase();

  if (t) {
    const localized = t(`roleLabels.${normalizedRole}`, { defaultValue: "" });
    if (localized) return localized;
  }

  return PROJECT_ROLE_LABELS[normalizedRole] ?? role;
}


