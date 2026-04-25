// =============================================================
// src/components/documents/pipeline/PipelineStageModal.tsx
// =============================================================

import React from "react";
import type {
  PipelineStageKind,
  PipelineStageViewDTO,
  StageViewMode,
  OpenViewerAtFn,
} from "../../../types";
import { getDocumentPipelineView } from "../../../api/documentPipelineView";
import { PdfStageViewer } from "./PdfStageViewer";
import { LayoutStageViewer } from "./LayoutStageViewer";
import { StructureStageViewer } from "./StructureStageViewer";
import { ChunksStageViewer } from "./ChunksStageViewer";
import { StageRepresentationBanner } from "./StageRepresentationBanner";

interface Props {
  stage: PipelineStageViewDTO | null;
  stages: PipelineStageViewDTO[];
  documentId: string;
  onOpenAtLocation?: OpenViewerAtFn;
  onClose: () => void;
}

// Список типов стадий, для которых реально есть смысл в friendly-режиме.
// Пока включаем только STRUCTURE, как обсуждали.
const FRIENDLY_SUPPORTED_KINDS: PipelineStageKind[] = ["structure"];

function supportsFriendlyMode(stage: PipelineStageViewDTO): boolean {
  return FRIENDLY_SUPPORTED_KINDS.includes(stage.kind);
}

function getErrorMessage(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const maybeDetail = (err as { detail?: unknown }).detail;
    if (typeof maybeDetail === "string" && maybeDetail.trim()) {
      return maybeDetail;
    }

    const maybeMessage = (err as { message?: unknown }).message;
    if (typeof maybeMessage === "string" && maybeMessage.trim()) {
      return maybeMessage;
    }
  }

  return "Не удалось переключить режим отображения стадии";
}

export const PipelineStageModal: React.FC<Props> = ({
  stage,
  stages,
  documentId,
  onOpenAtLocation,
  onClose,
}) => {
  // Текущая версия открытой стадии (может обновляться при переключении режима)
  const [currentStage, setCurrentStage] =
    React.useState<PipelineStageViewDTO | null>(stage);

  // Полный актуальный набор стадий для текущего view_mode.
  // Нужен, чтобы structure-viewer мог получить chunksStage.
  const [currentStages, setCurrentStages] =
    React.useState<PipelineStageViewDTO[]>(stages);

  // Локальный режим представления (canonical / friendly)
  const [viewMode, setViewMode] = React.useState<StageViewMode>("canonical");

  // Статусы загрузки/ошибки при переключении режима
  const [loading, setLoading] = React.useState<boolean>(false);
  const [error, setError] = React.useState<string | null>(null);

  // При смене входного stage (клик по другой строке в списке)
  // переинициализируем локальное состояние.
  React.useEffect(() => {
    setCurrentStage(stage || null);
    setCurrentStages(stages);
    setError(null);

    if (stage?.representation?.view_mode) {
      setViewMode(stage.representation.view_mode);
    } else {
      setViewMode("canonical");
    }
  }, [stage, stages]);

  // Если стадии нет, модалка не рендерится вообще.
  if (!currentStage) {
    return null;
  }

  const stageData: PipelineStageViewDTO = currentStage;
  const canToggleFriendly =
    supportsFriendlyMode(stageData) && stageData.status === "ready";

  async function handleToggleViewMode() {
    if (!documentId || !canToggleFriendly) return;

    const nextViewMode: StageViewMode =
      viewMode === "canonical" ? "friendly" : "canonical";

    try {
      setLoading(true);
      setError(null);

      const result = await getDocumentPipelineView(
        documentId,
        undefined,
        nextViewMode,
      );

      const updatedStage =
        result.stages.find((item) => item.code === stageData.code) ?? null;

      if (!updatedStage) {
        throw new Error(
          `Stage ${stageData.code} not found in pipeline response`,
        );
      }

      setCurrentStages(result.stages);
      setCurrentStage(updatedStage);
      setViewMode(nextViewMode);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function renderContent() {
    switch (stageData.kind) {
      case "pdf":
        return <PdfStageViewer stage={stageData} />;

      case "layout":
        return <LayoutStageViewer stage={stageData} />;

      case "structure": {
        const chunksStage =
          currentStages.find((item) => item.code === "CHUNKS") ?? null;

        return (
          <StructureStageViewer
            documentId={documentId}  
            structureStage={stageData}
            chunksStage={chunksStage}
            onOpenAtLocation={onOpenAtLocation}
          />
        );
      }

      case "chunks":
        return (
          <ChunksStageViewer 
            stage={stageData}
            documentId={documentId}
            onOpenAtLocation={onOpenAtLocation} 
          />
        );

      default:
        return (
          <div className="text-sm text-gray-500">
            Для этой стадии пока нет viewer.
          </div>
        );
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex h-[90vh] w-full max-w-7xl flex-col overflow-hidden rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between gap-4 border-b px-5 py-3">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-gray-500">
              {stageData.code}
            </p>
            <h2 className="text-base font-semibold text-gray-900">
              {stageData.title}
            </h2>
            <p className="mt-1 text-xs text-gray-500">
              {stageData.description}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {canToggleFriendly && (
              <button
                type="button"
                onClick={handleToggleViewMode}
                disabled={loading}
                className={`rounded border px-3 py-1.5 text-xs font-medium transition ${
                  loading
                    ? "cursor-not-allowed border-gray-200 bg-gray-50 text-gray-400"
                    : viewMode === "canonical"
                      ? "border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100"
                      : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                }`}
                title={
                  viewMode === "canonical"
                    ? "Показать более удобный для чтения вид"
                    : "Вернуться к каноническому результату этапа"
                }
              >
                {loading
                  ? "Переключение..."
                  : viewMode === "canonical"
                    ? "Показать friendly формат"
                    : "Показать canonical формат"}
              </button>
            )}

            <button
              type="button"
              onClick={onClose}
              className="rounded border px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            >
              Закрыть
            </button>
          </div>
        </div>

        <StageRepresentationBanner
          representation={stageData.representation}
          meta={stageData.meta ?? null}
        />

        {error && (
          <div className="mx-5 mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-auto p-5">{renderContent()}</div>
      </div>
    </div>
  );
};

export default PipelineStageModal;



