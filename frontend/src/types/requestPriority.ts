// =============================================================
// src/types/requestPriority.ts
// Normalized priority types for DD requests in UI.
// =============================================================

/**
 * Normalized DD request priority for UI consumption.
 * Used by tables, side panels, and badges.
 */
export type RequestPriority = "critical" | "high" | "medium" | "low";

/**
 * All possible raw values that backend may send for priority/severity
 * in review contexts (including pass/unclear and arbitrary strings).
 */
export type RawRequestPriority = string;

/**
 * Canonical order for sorting.
 * Lower number = higher priority.
 */
export const REQUEST_PRIORITY_ORDER: Record<RequestPriority, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export const REQUEST_PRIORITY_META: Record<
  RequestPriority,
  { label: string; labelKey: string }
> = {
  critical: { label: "Critical", labelKey: "common:priorities.critical" },
  high: { label: "High", labelKey: "common:priorities.high" },
  medium: { label: "Medium", labelKey: "common:priorities.medium" },
  low: { label: "Low", labelKey: "common:priorities.low" },
};

/**
 * Normalizes raw string from backend to RequestPriority.
 * - Unknown/soft statuses map to "medium" or "low".
 * - Behavior can be fine-tuned without touching UI code.
 */
export function normalizeRequestPriority(
  raw: RawRequestPriority | null | undefined,
): RequestPriority {
  if (!raw) return "medium";

  const v = raw.toLowerCase().trim();

  if (v === "critical") return "critical";
  if (v === "high") return "high";
  if (v === "medium") return "medium";
  if (v === "low") return "low";

  // Review severity may include pass/unclear values.
  if (v === "pass") return "low";
  if (v === "unclear") return "medium";

  // Soft/undefined variants are also treated as non-blocking.
  if (v === "warning") return "medium";
  if (v === "info") return "low";

  return "medium";
}


