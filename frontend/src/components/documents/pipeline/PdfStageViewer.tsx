import React from "react";
import type { PdfPreviewDTO, PipelineStageViewDTO } from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

/**
 * PdfStageViewer
 *
 * Показывает PDF-артефакт стадии:
 * - если есть inline_url — в iframe;
 * - если нет — сообщение, что встроенный просмотр недоступен;
 * - всегда оставляет ссылку "Открыть в новой вкладке", если есть download_url.
 *
 * Название/описание стадии рендерятся в шапке модалки,
 * поэтому здесь они не дублируются.
 */
export const PdfStageViewer: React.FC<Props> = ({ stage }) => {
  const preview = stage.preview as PdfPreviewDTO | null | undefined;

  if (!preview) {
    return (
      <div className="text-sm text-gray-500">
        PDF-превью недоступно.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-gray-500">
          {/* Небольшая подсказка вместо повторения title/description */}
          Исходный PDF этого этапа.
        </div>

        {preview.download_url && (
          <a
            href={preview.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded border text-xs font-medium text-gray-700 border-gray-200 hover:bg-gray-50"
          >
            Открыть в новой вкладке
          </a>
        )}
      </div>

      {preview.inline_url ? (
        <iframe
          title={`pipeline-stage-${stage.code}`}
          src={preview.inline_url}
          className="w-full flex-1 min-h-[70vh] border rounded-lg bg-white"
        />
      ) : (
        <div className="text-sm text-gray-500">
          PDF недоступен для встроенного просмотра.
        </div>
      )}
    </div>
  );
};

export default PdfStageViewer;

