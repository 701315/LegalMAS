import React from "react";
import type { PdfPreviewDTO, PipelineStageViewDTO } from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

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
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{stage.title}</h3>
          <p className="text-xs text-gray-500">{stage.description}</p>
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

