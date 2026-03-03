// =============================================================
// src/components/ui/SeverityBadge.tsx
// Бейдж уровня серьёзности (severity).
// =============================================================

import React from "react";
import type { SeverityLevel } from "../../types";

interface Props {
  severity: SeverityLevel;
  className?: string;
}

/**
 * Отображает уровень серьёзности:
 * - critical / high / medium / low / info
 */
export const SeverityBadge: React.FC<Props> = ({ severity, className }) => {
  let bg = "bg-gray-100 text-gray-700";
  let label: string = severity; // <- ЯВНО строка, не SeverityLevel

  switch (severity) {
    case "critical":
      bg = "bg-red-100 text-red-700";
      label = "Critical";
      break;
    case "high":
      bg = "bg-orange-100 text-orange-700";
      label = "High";
      break;
    case "medium":
      bg = "bg-yellow-100 text-yellow-700";
      label = "Medium";
      break;
    case "low":
      bg = "bg-green-100 text-green-700";
      label = "Low";
      break;
    case "info":
      bg = "bg-blue-100 text-blue-700";
      label = "Info";
      break;
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${bg} ${className ?? ""}`}
    >
      {label}
    </span>
  );
};
