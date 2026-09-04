// src/components/instructions/VersionStatusBadge.tsx
// Бейдж статуса версии инструкции.

import React from "react";
import { useTranslation } from "react-i18next";
import type { InstructionVersionStatus } from "../../types/instructions";

interface VersionStatusBadgeProps {
  status: InstructionVersionStatus | string;
  size?: "sm" | "xs";
}

const STATUS_CONFIG: Record<
  string,
  { labelKey: string; className: string }
> = {
  draft: {
    labelKey: "versionStatus.draft",
    className:
      "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
  },
  published: {
    labelKey: "versionStatus.published",
    className:
      "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
  },
  archived: {
    labelKey: "versionStatus.archived",
    className:
      "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
  },
};

const VersionStatusBadge: React.FC<VersionStatusBadgeProps> = ({
  status,
  size = "sm",
}) => {
  const { t } = useTranslation("instructions");

  const config = STATUS_CONFIG[status];
  const label = config ? t(config.labelKey) : status;
  const className =
    config?.className ??
    "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]";

  const sizeClass =
    size === "xs"
      ? "px-1.5 py-0.5 text-[10px] tracking-[0.1em]"
      : "px-2 py-0.5 text-[11px] tracking-[0.12em]";

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border font-semibold uppercase",
        sizeClass,
        className,
      ].join(" ")}
    >
      {label}
    </span>
  );
};

export default VersionStatusBadge;



