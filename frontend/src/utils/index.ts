// =============================================================
// src/utils/index.ts
// Shared utilities for frontend application.
// =============================================================

/**
 * Merges multiple CSS class names into a single string.
 * Example:
 *   className={cn("base", isActive && "active")}
 */
export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

/**
 * Formats an ISO date string according to the specified locale.
 */
export function formatDate(value?: string, locale?: string) {
  if (!value) return "";
  return new Date(value).toLocaleString(locale);
}

/**
 * Converts an ISO datetime into a relative human-readable string (e.g. "5m ago", "2h ago").
 * Supports an optional translation function tFn.
 */
export function timeAgo(
  value?: string,
  tFn?: (key: string, options?: Record<string, unknown>) => string,
) {
  if (!value) return "";
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.round(diff / 60000);

  if (minutes < 60) {
    return tFn
      ? tFn("common:timeAgo.minutes", { count: minutes })
      : `${minutes}m ago`;
  }

  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return tFn
      ? tFn("common:timeAgo.hours", { count: hours })
      : `${hours}h ago`;
  }

  const days = Math.round(hours / 24);
  return tFn
    ? tFn("common:timeAgo.days", { count: days })
    : `${days}d ago`;
}


