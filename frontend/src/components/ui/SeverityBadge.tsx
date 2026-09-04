// src/components/ui/SeverityBadge.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { twMerge } from "tailwind-merge";
import type { SeverityLevel } from "../../types";

interface Props {
  severity: SeverityLevel;
  className?: string;
}

type SeverityConfig = {
  labelKey: string;
  className: string;
};

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const SEVERITY_CONFIG: Record<SeverityLevel, SeverityConfig> = {
  critical: {
    labelKey: "severities.critical",
    className:
      "border-[var(--color-error-border)] " +
      "bg-[var(--color-error-bg)] " +
      "text-[var(--color-error-text)]",
  },
  high: {
    labelKey: "severities.high",
    className:
      "border-[var(--color-warning-border)] " +
      "bg-[var(--color-warning-bg)] " +
      "text-[var(--color-warning-text)]",
  },
  medium: {
    labelKey: "severities.medium",
    className:
      "border-[color:color-mix(in_oklab,var(--color-gold)_30%,transparent)] " +
      "bg-[var(--color-gold-highlight)] " +
      "text-[var(--color-gold-text)]",
  },
  pass: {
    labelKey: "severities.pass",
    className:
      "border-[var(--color-success-border)] " +
      "bg-[var(--color-success-bg)] " +
      "text-[var(--color-success-text)]",
  },
  unclear: {
    labelKey: "severities.unclear",
    className:
      "border-[color:color-mix(in_oklab,var(--color-blue)_30%,transparent)] " +
      "bg-[var(--color-blue-highlight)] " +
      "text-[var(--color-blue)]",
  },
};

const FALLBACK_CLASS =
  "border-[var(--border-subtle)] " +
  "bg-[var(--bg-subtle)] " +
  "text-[var(--text-secondary)]";

export const SeverityBadge: React.FC<Props> = ({ severity, className }) => {
  const { t } = useTranslation("common");
  const config = SEVERITY_CONFIG[severity];

  const label = config ? t(config.labelKey) : severity;
  const toneClass = config?.className ?? FALLBACK_CLASS;

  return (
    <span
      title={`Severity: ${label}`}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5",
        "text-[11px] font-medium leading-none whitespace-nowrap",
        toneClass,
        className,
      )}
    >
      {label}
    </span>
  );
};

export default SeverityBadge;


