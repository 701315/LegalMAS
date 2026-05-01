// src/types/requestPriority.ts

/**
 * Нормализованный приоритет DD‑запроса в UI.
 * Это то, с чем работают таблицы, side‑панели и badge.
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
  { label: string; colorClass: string }
> = {
  critical: {
    label: "Критичный",
    colorClass: "bg-red-100 text-red-800",
  },
  high: {
    label: "Высокий",
    colorClass: "bg-orange-100 text-orange-800",
  },
  medium: {
    label: "Средний",
    colorClass: "bg-yellow-100 text-yellow-800",
  },
  low: {
    label: "Низкий",
    colorClass: "bg-gray-100 text-gray-800",
  },
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

  // Если backend каким‑то образом прислал "low" — поддерживаем.
  if (v === "low") return "low";

  // В review severity могут приходить pass/unclear — считаем их низким/средним приоритетом.
  if (v === "pass") return "low";
  if (v === "unclear") return "medium";

  // Любое другое значение считаем средним.
  return "medium";
}

