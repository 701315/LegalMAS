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

interface RequestPriorityBadgeProps {
  priority: "critical" | "high" | "medium";
  /**
   * Размер badge.
   * - "sm" — для таблиц (компактный)
   * - "md" — для side panel (обычный)
   */
  size?: "sm" | "md";
}

/**
 * Отображает цветную плашку с приоритетом запроса.
 * Цвета:
 * - critical (критичный) → красный
 * - high (высокий) → оранжевый
 * - medium (средний) → жёлтый
 */
export const RequestPriorityBadge: React.FC<RequestPriorityBadgeProps> = ({
  priority,
  size = "md",
}) => {
  // Конфигурация для каждого приоритета
  const config = {
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
  };

  const { label, colorClass } = config[priority];

  // Размеры badge
  const sizeClass = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2 py-1 text-xs";

  return (
    <span
      className={`inline-block rounded font-semibold ${colorClass} ${sizeClass}`}
    >
      {label}
    </span>
  );
};

export default RequestPriorityBadge;

