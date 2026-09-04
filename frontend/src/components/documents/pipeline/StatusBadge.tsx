// src/components/documents/pipeline/StatusBadge.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { twMerge } from "tailwind-merge";
import type { PipelineStageStatus } from "../../../types";

interface Props {
  status: PipelineStageStatus;
  className?: string;
}

type StatusStyleConfig = {
  labelKey: string;
  titleKey: string;
  className: string;
};

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const STATUS_STYLE_CONFIG: Record<PipelineStageStatus, StatusStyleConfig> = {
  ready: {
    labelKey: "stageStatusBadge.ready.label",
    titleKey: "stageStatusBadge.ready.title",
    className:
      "border-[var(--color-success-border)] " +
      "bg-[var(--color-success-bg)] " +
      "text-[var(--color-success-text)]",
  },
  pending: {
    labelKey: "stageStatusBadge.pending.label",
    titleKey: "stageStatusBadge.pending.title",
    className:
      "border-[var(--color-warning-border)] " +
      "bg-[var(--color-warning-bg)] " +
      "text-[var(--color-warning-text)]",
  },
  missing: {
    labelKey: "stageStatusBadge.missing.label",
    titleKey: "stageStatusBadge.missing.title",
    className:
      "border-[var(--color-error-border)] " +
      "bg-[var(--color-error-bg)] " +
      "text-[var(--color-error-text)]",
  },
};

export const StatusBadge: React.FC<Props> = ({ status, className }) => {
  const { t } = useTranslation("pipeline");
  const cfg = STATUS_STYLE_CONFIG[status];

  if (!cfg) {
    return null;
  }

  return (
    <span
      title={t(cfg.titleKey)}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap",
        cfg.className,
        className,
      )}
    >
      {t(cfg.labelKey)}
    </span>
  );
};

export default StatusBadge;


