// =============================================================
// src/components/documents/pipeline/StatusBadge.tsx
// =============================================================

import React from "react";
import type { PipelineStageStatus } from "../../../types";

interface Props {
  status: PipelineStageStatus;
}

const STATUS_CONFIG: Record<
  PipelineStageStatus,
  { label: string; title: string; className: string }
> = {
  ready: {
    label: "Готово",
    title: "Артефакт стадии готов к просмотру",
    className: "bg-green-50 text-green-700 border border-green-200",
  },
  pending: {
    label: "Ожидается",
    title: "Стадия ещё не завершена или артефакт пока не подготовлен",
    className: "bg-yellow-50 text-yellow-800 border border-yellow-200",
  },
  missing: {
    label: "Недоступно",
    title: "Артефакт стадии не найден",
    className: "bg-red-50 text-red-700 border border-red-200",
  },
};

export const StatusBadge: React.FC<Props> = ({ status }) => {
  const cfg = STATUS_CONFIG[status];

  return (
    <span
      title={cfg.title}
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${cfg.className}`}
    >
      {cfg.label}
    </span>
  );
};

export default StatusBadge;

