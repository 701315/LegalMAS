// =============================================================
// src/components/ui/ClassificationBadge.tsx
// =============================================================

import React from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("pipeline");

  if (!level) return null;

  const meta = CLASSIFICATION_LEVELS[level] || CLASSIFICATION_LEVELS.L0;

  // Безопасное приведение к расширенному типу с i18n-ключами
  const metaWithKeys = meta as {
    label: string;
    shortLabel: string;
    description: string;
    badgeClassName: string;
    labelKey?: string;
    shortLabelKey?: string;
    descriptionKey?: string;
  };

  // Динамически разрешаем переводы по ключам дескрипторов, если они есть.
  // Если ключей нет в типе констант — используем базовые fallback строки.
  const label = metaWithKeys.labelKey ? t(metaWithKeys.labelKey) : meta.label;
  const shortLabel = metaWithKeys.shortLabelKey ? t(metaWithKeys.shortLabelKey) : meta.shortLabel;
  const description = metaWithKeys.descriptionKey ? t(metaWithKeys.descriptionKey) : meta.description;

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
      title={`${label}. ${description}`}
    >
      {isLowConfidence && (
        <AlertTriangle
          size={11}
          className="text-[var(--color-gold-text)]"
          aria-hidden="true"
        />
      )}

      <span>{shortLabel}</span>

      {showConfidence && confidence !== undefined && confidence !== null && (
        <span className="ml-0.5 opacity-75">
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
};

export default ClassificationBadge;


