// =============================================================
// src/components/documents/pipeline/PipelineStageRow.tsx
// =============================================================

import React from "react";
import type { PipelineStageViewDTO } from "../../../types";
import { StatusBadge } from "./StatusBadge";
import Button from "../../ui/Button";

interface Props {
  stage: PipelineStageViewDTO;
  onOpen: (stage: PipelineStageViewDTO) => void;
}

function buildMetaLine(stage: PipelineStageViewDTO): string | null {
  const meta = stage.meta;
  if (!meta) return null;

  const parts: string[] = [];

  if (typeof meta.page_count === "number") {
    parts.push(`стр.: ${meta.page_count}`);
  }
  if (typeof meta.element_count === "number") {
    parts.push(`элементов: ${meta.element_count}`);
  }
  if (typeof meta.section_count === "number") {
    parts.push(`секций: ${meta.section_count}`);
  }
  if (typeof meta.chunk_count === "number") {
    parts.push(`чанков: ${meta.chunk_count}`);
  }
  if (meta.source_file_name) {
    parts.push(meta.source_file_name);
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

function getOpenDisabledReason(stage: PipelineStageViewDTO): string {
  if (stage.status === "pending") {
    return "Стадия ещё не готова";
  }

  if (stage.status === "missing") {
    return "Артефакт стадии недоступен или повреждён";
  }

  if (!stage.available) {
    return "Стадия недоступна для просмотра";
  }

  return "Стадия пока недоступна для просмотра";
}

export const PipelineStageRow: React.FC<Props> = ({ stage, onOpen }) => {
  const canOpen = stage.available && stage.status === "ready";
  const metaLine = buildMetaLine(stage);

  return (
    <div className="flex items-start justify-between gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 shadow-sm transition-shadow hover:shadow-md">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">
            {stage.code}
          </span>

          <StatusBadge status={stage.status} />
        </div>

        <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
          {stage.title}
        </p>

        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          {stage.description}
        </p>

        {metaLine && (
          <p className="mt-2 text-[11px] text-[var(--text-muted)]">{metaLine}</p>
        )}
      </div>

      <div className="shrink-0">
        <Button
          type="button"
          size="sm"
          variant={canOpen ? "secondary" : "ghost"}
          disabled={!canOpen}
          onClick={() => onOpen(stage)}
          title={canOpen ? "Открыть стадию" : getOpenDisabledReason(stage)}
        >
          Открыть
        </Button>
      </div>
    </div>
  );
};

export default PipelineStageRow;



