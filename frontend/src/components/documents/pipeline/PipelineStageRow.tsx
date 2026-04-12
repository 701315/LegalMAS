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

export const PipelineStageRow: React.FC<Props> = ({ stage, onOpen }) => {
  const canOpen = stage.available && stage.status === "ready";
  const metaLine = buildMetaLine(stage);

  return (
    <div className="flex items-start justify-between gap-3 border border-gray-100 rounded-lg p-3 bg-white">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            {stage.code}
          </span>

          <StatusBadge status={stage.status} />
        </div>

        <p className="mt-1 text-sm font-medium text-gray-900">{stage.title}</p>

        <p className="mt-1 text-xs text-gray-500 leading-5">
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
          title={
            canOpen
              ? "Открыть стадию"
              : "Стадия пока недоступна для просмотра"
          }
          className="px-3 py-1.5 rounded border text-xs font-medium transition disabled:opacity-50 disabled:cursor-not-allowed text-gray-700 border-gray-200 hover:bg-gray-50"
        >
          Открыть
        </button>
      </div>
    </div>
  );
};

export default PipelineStageRow;

