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

const LANGUAGE_LABELS: Record<string, string> = {
  RU: "Русский (RU)",
  EN: "English (EN)",
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

export function formatLangLabel(value: string | null | undefined): string {
  const lang = normalizeLang(value);

  if (!lang) {
    return "";
  }

  return LANGUAGE_LABELS[lang] ?? lang;
}


