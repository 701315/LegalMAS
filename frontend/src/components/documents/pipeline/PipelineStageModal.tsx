import React from "react";
import type { PipelineStageViewDTO } from "../../../types";
import { PdfStageViewer } from "./PdfStageViewer";
import { LayoutStageViewer } from "./LayoutStageViewer";
import { StructureStageViewer } from "./StructureStageViewer";
import { ChunksStageViewer } from "./ChunksStageViewer";

interface Props {
  stage: PipelineStageViewDTO | null;
  onClose: () => void;
}

export const PipelineStageModal: React.FC<Props> = ({ stage, onClose }) => {
  if (!stage) return null;

  const renderContent = () => {
    switch (stage.kind) {
      case "pdf":
        return <PdfStageViewer stage={stage} />;
      case "layout":
        return <LayoutStageViewer stage={stage} />;
      case "structure":
        return <StructureStageViewer stage={stage} />;
      case "chunks":
        return <ChunksStageViewer stage={stage} />;
      default:
        return (
          <div className="text-sm text-gray-500">
            Для этой стадии пока нет viewer.
          </div>
        );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-7xl h-[90vh] bg-white rounded-xl shadow-xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div>
            <p className="text-xs uppercase tracking-wide text-gray-500">
              {stage.code}
            </p>
            <h2 className="text-base font-semibold text-gray-900">
              {stage.title}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-600 border rounded hover:bg-gray-50"
          >
            Закрыть
          </button>
        </div>

        <div className="flex-1 overflow-auto p-5">{renderContent()}</div>
      </div>
    </div>
  );
};

export default PipelineStageModal;


