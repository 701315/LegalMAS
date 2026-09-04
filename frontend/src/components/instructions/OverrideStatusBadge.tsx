// src/components/instructions/OverrideStatusBadge.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import type { OverrideStatus } from "../../types/instructions";

interface OverrideStatusBadgeProps {
  status: OverrideStatus;
  isStale?: boolean;
  size?: "sm" | "xs";
}

const STATUS_STYLE_CONFIG: Record<
  OverrideStatus,
  { labelKey: string; className: string }
> = {
  draft: {
    labelKey: "overrideStatusBadge.draft",
    className:
      "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
  },
  active: {
    labelKey: "overrideStatusBadge.active",
    className:
      "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
  },
  archived: {
    labelKey: "overrideStatusBadge.archived",
    className:
      "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
  },
};

const OverrideStatusBadge: React.FC<OverrideStatusBadgeProps> = ({
  status,
  isStale = false,
  size = "sm",
}) => {
  const { t } = useTranslation("instructions");
  const config = STATUS_STYLE_CONFIG[status];
  const sizeClass =
    size === "xs"
      ? "px-1.5 py-0.5 text-[10px] tracking-[0.1em]"
      : "px-2 py-0.5 text-[11px] tracking-[0.12em]";

  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={[
          "inline-flex items-center rounded-full border font-semibold uppercase",
          sizeClass,
          config?.className ?? "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
        ].join(" ")}
      >
        {config ? t(config.labelKey) : status}
      </span>
      {isStale && (
        <span
          className={[
            "inline-flex items-center rounded-full border font-semibold uppercase",
            sizeClass,
            "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
          ].join(" ")}
        >
          {t("overrideStatusBadge.stale")}
        </span>
      )}
    </span>
  );
};

export default OverrideStatusBadge;


