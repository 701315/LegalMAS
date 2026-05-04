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

// Используем семантические цветовые токены с fallback’ами
const SEVERITY_CONFIG: Record<SeverityLevel, SeverityConfig> = {
  critical: {
    label: "Critical",
    className:
      "border-[color:color-mix(in_oklab,var(--color-error)_40%,transparent)] " +
      "bg-[var(--color-error-highlight,#fef2f2)] " +
      "text-[var(--color-error,#b91c1c)]",
  },
  high: {
    label: "High",
    className:
      "border-[color:color-mix(in_oklab,var(--color-orange)_35%,transparent)] " +
      "bg-[var(--color-orange-highlight,#fff7ed)] " +
      "text-[var(--color-orange,#c2410c)]",
  },
  medium: {
    label: "Medium",
    className:
      "border-[color:color-mix(in_oklab,var(--color-gold)_30%,transparent)] " +
      "bg-[var(--color-gold-highlight,#fefce8)] " +
      "text-[var(--color-gold-hover,#854d0e)]",
  },
  pass: {
    label: "Pass",
    className:
      "border-[color:color-mix(in_oklab,var(--color-success)_30%,transparent)] " +
      "bg-[var(--color-success-highlight,#f0fdf4)] " +
      "text-[var(--color-success,#15803d)]",
  },
  unclear: {
    label: "Unclear",
    className:
      "border-[color:color-mix(in_oklab,var(--color-blue)_30%,transparent)] " +
      "bg-[var(--color-blue-highlight,#eff6ff)] " +
      "text-[var(--color-blue,#1d4ed8)]",
  },
};

export const SeverityBadge: React.FC<Props> = ({ severity, className }) => {
  const config =
    SEVERITY_CONFIG[severity] ?? {
      label: severity,
      className:
        "border-[var(--border-subtle,#e5e7eb)] " +
        "bg-[var(--bg-subtle,#f9fafb)] " +
        "text-[var(--text-secondary,#6b7280)]",
    };

  return (
    <span
      title={`Severity: ${config.label}`}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
};

export default SeverityBadge;


