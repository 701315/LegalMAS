// src/types/requestPriority.ts

/**
 * Нормализованный приоритет DD-запроса в UI.
 * Это то, с чем работают таблицы, side-панели и badge.
 */
export type RequestPriority = "critical" | "high" | "medium" | "low";

/**
 * Весь зоопарк того, что может прислать backend в priority/severity
 * для review (включая pass/unclear и произвольные строки).
 */
export type RawRequestPriority = string;

/**
 * Канонический порядок для сортировки.
 * Чем меньше число — тем выше приоритет.
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
 * Нормализуем raw string из backend в RequestPriority.
 * - Всё неизвестное/мягкие статусы мапим в "medium" или "low".
 * - Поведение можно тонко подстроить, не трогая UI.
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

  // В review severity могут приходить pass/unclear.
  if (v === "pass") return "low";
  if (v === "unclear") return "medium";

  // Мягкие/неопределённые варианты тоже считаем неблокирующими.
  if (v === "warning") return "medium";
  if (v === "info") return "low";

  return "medium";
}


