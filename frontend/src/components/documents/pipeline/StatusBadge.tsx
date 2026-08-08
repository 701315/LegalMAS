// src/components/documents/pipeline/StatusBadge.tsx

import React from "react";
import { twMerge } from "tailwind-merge";
import type { PipelineStageStatus } from "../../../types";

interface Props {
  status: PipelineStageStatus;
  className?: string;
}

type StatusConfig = {
  label: string;
  title: string;
  className: string;
};

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const STATUS_CONFIG: Record<PipelineStageStatus, StatusConfig> = {
  ready: {
    label: "Готово",
    title: "Артефакт стадии готов к просмотру",
    className:
      "border-[var(--color-success-border)] " +
      "bg-[var(--color-success-bg)] " +
      "text-[var(--color-success-text)]",
  },
  pending: {
    label: "Ожидается",
    title: "Стадия ещё не завершена или артефакт пока не подготовлен",
    className:
      "border-[var(--color-warning-border)] " +
      "bg-[var(--color-warning-bg)] " +
      "text-[var(--color-warning-text)]",
  },
  missing: {
    label: "Недоступно",
    title: "Артефакт стадии не найден",
    className:
      "border-[var(--color-error-border)] " +
      "bg-[var(--color-error-bg)] " +
      "text-[var(--color-error-text)]",
  },
};

export const StatusBadge: React.FC<Props> = ({ status, className }) => {
  const cfg = STATUS_CONFIG[status];

  return (
    <span
      title={cfg.title}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap",
        cfg.className,
        className,
      )}
    >
      {cfg.label}
    </span>
  );
};

export default StatusBadge;


