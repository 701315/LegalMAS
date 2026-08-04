// =============================================================
// src/components/ui/ClassificationBadge.tsx
// =============================================================

import React from "react";
import { AlertTriangle } from "lucide-react";
import { CLASSIFICATION_LEVELS, CONFIDENCE_THRESHOLDS } from "../../constants";
import type { ClassificationLevel } from "../../types";

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

interface Props {
  level?: ClassificationLevel | null;
  confidence?: number | null;
  showConfidence?: boolean;
  className?: string;
}

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
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium leading-none",
        meta.badgeClassName,
        isLowConfidence && "ring-1 ring-[var(--color-gold)]/35",
        className,
      )}
      title={`${meta.label}. ${meta.description}`}
    >
      {isLowConfidence && (
        <AlertTriangle
          size={11}
          className="text-[var(--color-gold-text)]"
          aria-hidden="true"
        />
      )}

      <span>{meta.shortLabel}</span>

      {showConfidence && confidence !== undefined && confidence !== null && (
        <span className="ml-0.5 opacity-75">
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
};


