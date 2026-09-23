// src/components/ui/CellRiskBadge.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { twMerge } from "tailwind-merge";

export type CellRiskLevel = "high" | "medium" | "low" | "info";

interface Props {
  level: CellRiskLevel | null;
  topField?: string | null;
  topValue?: string | null;
  topDisplay?: string | null;
  className?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const LEVEL_CLASS: Record<CellRiskLevel, string> = {
  high:
    "border-[var(--color-error-border)] " +
    "bg-[var(--color-error-bg)] " +
    "text-[var(--color-error-text)]",
  medium:
    "border-[var(--color-warning-border)] " +
    "bg-[var(--color-warning-bg)] " +
    "text-[var(--color-warning-text)]",
  low:
    "border-[var(--color-blue-soft-border)] " +
    "bg-[var(--color-blue-soft-bg)] " +
    "text-[var(--color-blue-strong)]",
  info:
    "border-[var(--border-subtle)] " +
    "bg-[var(--bg-elevated-soft)] " +
    "text-[var(--text-secondary)]",
};

export const CellRiskBadge: React.FC<Props> = ({
  level,
  topField,
  topValue,
  topDisplay,
  className,
}) => {
  const { t } = useTranslation("ddGrid");

  if (level === null) {
    return null;
  }

  const label = t(`riskWeight.${level}`);
  const tone = LEVEL_CLASS[level];

  const tooltip = topField
    ? t("riskWeight.tooltip", {
        level: label,
        field: topField,
        value: topDisplay || topValue || "",
      })
    : label;

  return (
    <span
      title={tooltip}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5",
        "text-[10px] font-semibold leading-none whitespace-nowrap",
        tone,
        className,
      )}
    >
      {label}
    </span>
  );
};

export default CellRiskBadge;
