// src/components/ui/SeverityBadge.tsx

import React from "react";
import { twMerge } from "tailwind-merge";
import type { SeverityLevel } from "../../types";

interface Props {
  severity: SeverityLevel;
  className?: string;
}

type SeverityConfig = {
  label: string;
  className: string;
};

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const SEVERITY_CONFIG: Record<SeverityLevel, SeverityConfig> = {
  critical: {
    label: "Critical",
    className:
      "border-[var(--color-error-border)] " +
      "bg-[var(--color-error-bg)] " +
      "text-[var(--color-error-text)]",
  },
  high: {
    label: "High",
    className:
      "border-[var(--color-warning-border)] " +
      "bg-[var(--color-warning-bg)] " +
      "text-[var(--color-warning-text)]",
  },
  medium: {
    label: "Medium",
    className:
      "border-[color:color-mix(in_oklab,var(--color-gold)_30%,transparent)] " +
      "bg-[var(--color-gold-highlight)] " +
      "text-[var(--color-gold-text)]",
  },
  pass: {
    label: "Pass",
    className:
      "border-[var(--color-success-border)] " +
      "bg-[var(--color-success-bg)] " +
      "text-[var(--color-success-text)]",
  },
  unclear: {
    label: "Unclear",
    className:
      "border-[color:color-mix(in_oklab,var(--color-blue)_30%,transparent)] " +
      "bg-[var(--color-blue-highlight)] " +
      "text-[var(--color-blue)]",
  },
};

const FALLBACK_CONFIG: SeverityConfig = {
  label: "",
  className:
    "border-[var(--border-subtle)] " +
    "bg-[var(--bg-subtle)] " +
    "text-[var(--text-secondary)]",
};

export const SeverityBadge: React.FC<Props> = ({ severity, className }) => {
  const config = SEVERITY_CONFIG[severity] ?? {
    ...FALLBACK_CONFIG,
    label: severity,
  };

  return (
    <span
      title={`Severity: ${config.label}`}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5",
        "text-[11px] font-medium leading-none whitespace-nowrap",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
};

export default SeverityBadge;


