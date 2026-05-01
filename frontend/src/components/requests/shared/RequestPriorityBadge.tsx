// =============================================================
// src/components/requests/shared/RequestPriorityBadge.tsx
// Shared UI компонент для отображения приоритета DD-запроса.
// Используется в:
// - RequestsTable (legacy)
// - ReviewRequestsTable (review)
// - RequestSidePanel (legacy)
// - ReviewRequestSidePanel (review)
//
// Для непрофессионального программиста:
// Это маленький компонент-"плашка" с цветом и текстом приоритета.
// Один и тот же компонент работает и в старом, и в новом режиме.
// =============================================================

import React from "react";
import type { RequestPriority } from "../../../types/requestPriority";
import { REQUEST_PRIORITY_META } from "../../../types/requestPriority";

interface RequestPriorityBadgeProps {
  priority: RequestPriority;
  /**
   * Размер badge.
   * - "sm" — для таблиц (компактный)
   * - "md" — для side panel (обычный)
   */
  size?: "sm" | "md";
  className?: string;
}

/**
 * Отображает цветную плашку с приоритетом запроса.
 *
 * Важно:
 * - Компонент работает только с нормализованным UI-типом RequestPriority.
 * - Вся доменная семантика (label, color) хранится централизованно
 *   в REQUEST_PRIORITY_META.
 * - Если по какой-то причине priority окажется некорректным во runtime,
 *   используем безопасный fallback на "medium".
 */
export const RequestPriorityBadge: React.FC<RequestPriorityBadgeProps> = ({
  priority,
  size = "md",
  className = "",
}) => {
  const config =
    REQUEST_PRIORITY_META[priority] ?? REQUEST_PRIORITY_META.medium;

  const sizeClass =
    size === "sm"
      ? "px-2 py-0.5 text-xs"
      : "px-2 py-1 text-xs";

  return (
    <span
      className={[
        "inline-flex items-center rounded font-semibold whitespace-nowrap",
        config.colorClass,
        sizeClass,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      title={`Приоритет: ${config.label}`}
    >
      {config.label}
    </span>
  );
};

export default RequestPriorityBadge;

