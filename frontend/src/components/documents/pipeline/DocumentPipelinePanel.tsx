import React from "react";
import type {
  DocumentPipelineViewResponseDTO,
  PipelineStageViewDTO,
  StageViewMode,
} from "../../../types";
import { getDocumentPipelineView } from "../../../api/documentPipelineView";
import { PipelineStageRow } from "./PipelineStageRow";
import { PipelineStageModal } from "./PipelineStageModal";

interface Props {
  documentId: string;
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

  return "Не удалось загрузить стадии документа";
}

export const DocumentPipelinePanel: React.FC<Props> = ({ documentId }) => {
  const [data, setData] =
    React.useState<DocumentPipelineViewResponseDTO | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedStage, setSelectedStage] =
    React.useState<PipelineStageViewDTO | null>(null);

  const [viewMode, setViewMode] = React.useState<StageViewMode>("canonical");

  React.useEffect(() => {
    const controller = new AbortController();

    async function load() {
      if (!documentId) {
        setData(null);
        setSelectedStage(null);
        setError("Не указан идентификатор документа");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        setData(null);
        setSelectedStage(null);

        const result = await getDocumentPipelineView(
          documentId,
          controller.signal,
          viewMode,
        );

        setData(result);
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }

        setError(getErrorMessage(err));
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      controller.abort();
    };
  }, [documentId, viewMode]);

  const effectiveViewMode: StageViewMode | null = data?.view_mode ?? null;

  return (
    <>
      <div className="space-y-3">
        <div>
          <p className="text-xs text-gray-500 mb-1">
            SOURCE → PRIMARY → EXTRACT → PII → STRUCTURE → CHUNKS
          </p>
          <p className="text-xs text-gray-400">
            Здесь отображается путь документа по стадиям обработки — от
            исходного PDF до структуры и чанков.
          </p>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="text-xs text-gray-500">
            Режим представления пайплайна:
          </div>

          <div className="inline-flex rounded border border-gray-200 bg-gray-50 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("canonical")}
              className={`px-2 py-1 rounded ${
                viewMode === "canonical"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              canonical
            </button>
            <button
              type="button"
              onClick={() => setViewMode("friendly")}
              className={`px-2 py-1 rounded ${
                viewMode === "friendly"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              friendly
            </button>
          </div>
        </div>

        {effectiveViewMode && (
          <p className="text-[11px] text-gray-400">
            Текущий режим (по данным сервера): {effectiveViewMode}
          </p>
        )}

        {loading && (
          <div className="text-sm text-gray-500">
            Загрузка стадий обработки…
          </div>
        )}

        {!loading && error && (
          <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {!loading && !error && data && data.stages.length > 0 && (
          <div className="space-y-2">
            {data.stages.map((stage) => (
              <PipelineStageRow
                key={stage.code}
                stage={stage}
                onOpen={setSelectedStage}
              />
            ))}
          </div>
        )}

        {!loading && !error && data && data.stages.length === 0 && (
          <div className="text-sm text-gray-500">
            Стадии обработки пока недоступны.
          </div>
        )}
      </div>

      <PipelineStageModal
        stage={selectedStage}
        onClose={() => setSelectedStage(null)}
      />
    </>
  );
};

export default DocumentPipelinePanel;

