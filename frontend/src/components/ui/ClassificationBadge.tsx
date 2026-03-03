// =============================================================
// src/components/ui/ClassificationBadge.tsx
// Бейдж уровня классификации документа (L0–L4, L_manual) + confidence.
// =============================================================

import React from "react";
import { AlertTriangle } from "lucide-react";
import { CLASSIFICATION_LEVELS, CONFIDENCE_THRESHOLDS } from "../../constants";
import type { ClassificationLevel } from "../../types";

// Вспомогательная функция объединения className (простая версия)
function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

interface Props {
  level?: ClassificationLevel | null;
  confidence?: number | null;
  showConfidence?: boolean;
  className?: string;
}

/**
 * Показывает:
 * - уровень (L0–L4 / L_manual)
 * - процент уверенности (если есть)
 * - жёлтый треугольник, если confidence < LOW (0.6)
 */
export const ClassificationBadge: React.FC<Props> = ({
  level,
  confidence,
  showConfidence = true,
  className,
}) => {
  if (!level) return null;

  const meta = CLASSIFICATION_LEVELS[level] || CLASSIFICATION_LEVELS.L0;

  const isLowConfidence =
    confidence !== undefined &&
    confidence !== null &&
    confidence > 0 &&
    confidence < CONFIDENCE_THRESHOLDS.LOW;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium",
        meta.color,
        isLowConfidence && "ring-1 ring-yellow-400",
        className,
      )}
      title={meta.description}
    >
      {isLowConfidence && (
        <AlertTriangle size={11} className="text-yellow-600" />
      )}
      {level}
      {showConfidence && confidence !== undefined && confidence !== null && (
        <span className="opacity-75 ml-0.5">
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
};
