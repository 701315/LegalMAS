// =============================================================
// src/utils/index.ts
// Общие утилиты для фронтенда MAS-DD.
// =============================================================

/**
 * Объединяет несколько className в одну строку.
 * Удобно использовать в компонентах:
 *   className={cn("base", isActive && "active")}
 */
export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

/**
 * Форматирование даты в локальный формат.
 * Принимает строку с датой (ISO) и возвращает человекочитаемую дату/время.
 */
export function formatDate(value?: string, locale?: string) {
  if (!value) return "";
  return new Date(value).toLocaleString(locale);
}

/**
 * Преобразует дату во фразу вида "5 мин назад", "2 ч назад", "3 дн назад".
 * Поддерживает опциональную функцию интернационализации tFn.
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


