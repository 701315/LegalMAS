// src/components/instructions/VersionStatusBadge.tsx
// Бейдж статуса версии инструкции.

import React from "react";
import type { InstructionVersionStatus } from "../../types/instructions";

interface VersionStatusBadgeProps {
  status: InstructionVersionStatus | string;
  size?: "sm" | "xs";
}

const STATUS_CONFIG: Record<
  string,
  { label: string; className: string }
> = {
  draft: {
    label: "Draft",
    className:
      "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
  },
  published: {
    label: "Published",
    className:
      "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
  },
  archived: {
    label: "Archived",
    className:
      "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
  },
};

const VersionStatusBadge: React.FC<VersionStatusBadgeProps> = ({
  status,
  size = "sm",
}) => {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className:
      "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
  };

  const sizeClass =
    size === "xs"
      ? "px-1.5 py-0.5 text-[10px] tracking-[0.1em]"
      : "px-2 py-0.5 text-[11px] tracking-[0.12em]";

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border font-semibold uppercase",
        sizeClass,
        config.className,
      ].join(" ")}
    >
      {config.label}
    </span>
  );
};

export default VersionStatusBadge;


