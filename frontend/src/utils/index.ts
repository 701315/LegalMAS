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
export function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleString();
}

/**
 * Преобразует дату во фразу вида "5 мин назад", "2 ч назад", "3 дн назад".
 */
export function timeAgo(value?: string) {
  if (!value) return "";
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.round(hours / 24);
  return `${days} дн назад`;
}
