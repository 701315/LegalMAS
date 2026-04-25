// =============================================================
// src/components/documents/pipeline/PipelineStageRow.tsx
// =============================================================

import React from "react";
import type { PipelineStageViewDTO } from "../../../types";
import { StatusBadge } from "./StatusBadge";

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
    <div className="flex items-start justify-between gap-3 rounded-lg border border-gray-100 bg-white p-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            {stage.code}
          </span>

          <StatusBadge status={stage.status} />
        </div>

        <p className="mt-1 text-sm font-medium text-gray-900">{stage.title}</p>

        <p className="mt-1 text-xs leading-5 text-gray-500">
          {stage.description}
        </p>

        {metaLine && (
          <p className="mt-2 text-[11px] text-gray-400">{metaLine}</p>
        )}
      </div>

      <div className="shrink-0">
        <button
          type="button"
          disabled={!canOpen}
          onClick={() => onOpen(stage)}
          title={canOpen ? "Открыть стадию" : getOpenDisabledReason(stage)}
          className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Открыть
        </button>
      </div>
    </div>
  );
};

export default PipelineStageRow;



