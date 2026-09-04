// =============================================================
// src/utils/languageDiscovery.ts
// =============================================================

import type { DealLanguageDiscoveryStatus } from "../types";

const KNOWN_DISCOVERY_STATUSES: readonly DealLanguageDiscoveryStatus[] = [
  "pending",
  "processing",
  "completed",
  "failed",
  "partial",
] as const;

const KNOWN_DISCOVERY_STATUS_SET = new Set<string>(KNOWN_DISCOVERY_STATUSES);

/** Canonical English fallback labels. */
const LANGUAGE_LABELS: Record<string, string> = {
  RU: "Russian (RU)",
  EN: "English (EN)",
};

/** i18n keys for supported language codes. */
export const LANGUAGE_LABEL_KEYS: Record<string, string> = {
  RU: "common:languages.RU",
  EN: "common:languages.EN",
};

export function normalizeDiscoveryStatus(
  value: string | null | undefined,
): DealLanguageDiscoveryStatus | string | null {
  const normalized = String(value ?? "").trim().toLowerCase();

  if (!normalized) {
    return null;
  }

  if (KNOWN_DISCOVERY_STATUS_SET.has(normalized)) {
    return normalized as DealLanguageDiscoveryStatus;
  }

  // Сохраняем forward-compatibility:
  // если backend когда-то вернёт новый статус, UI не сломается молча.
  return normalized;
}

export function shouldPollDealLanguageDiscovery(
  status: string | null | undefined,
): boolean {
  const normalizedStatus = normalizeDiscoveryStatus(status);
  return normalizedStatus === "pending" || normalizedStatus === "processing";
}

export function normalizeLang(value: string | null | undefined): string {
  return String(value ?? "").trim().toUpperCase();
}

/**
 * Formats a language code into a human-readable label.
 * Supports an optional translation function (tFn).
 */
export function formatLangLabel(
  value: string | null | undefined,
  tFn?: (key: string, options?: Record<string, unknown>) => string,
): string {
  const lang = normalizeLang(value);

  if (!lang) {
    return "";
  }

  if (tFn) {
    const key = LANGUAGE_LABEL_KEYS[lang] ?? `common:languages.${lang}`;
    const localized = tFn(key, { defaultValue: "" });
    if (localized) {
      return localized;
    }
  }

  return LANGUAGE_LABELS[lang] ?? lang;
}


