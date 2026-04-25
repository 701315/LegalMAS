// =============================================================
// src/components/documents/pipeline/DocumentPipelinePanel.tsx
// =============================================================


import React from "react";
import type {
  DocumentPipelineViewResponseDTO,
  PipelineStageViewDTO,
  OpenViewerAtFn,
} from "../../../types";
import { getDocumentPipelineView } from "../../../api/documentPipelineView";
import { PipelineStageRow } from "./PipelineStageRow";
import { PipelineStageModal } from "./PipelineStageModal";

interface Props {
  documentId: string;
  onOpenAtLocation?: OpenViewerAtFn;
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

export const DocumentPipelinePanel: React.FC<Props> = ({
  documentId,
  onOpenAtLocation,
}) => {
  const [data, setData] =
    React.useState<DocumentPipelineViewResponseDTO | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedStage, setSelectedStage] =
    React.useState<PipelineStageViewDTO | null>(null);

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

        // Панель всегда загружает pipeline в canonical-режиме по умолчанию.
        // Переключение в friendly будет происходить внутри modal конкретной стадии.
        const result = await getDocumentPipelineView(documentId, controller.signal);

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
  }, [documentId]);

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
        stages={data?.stages ?? []}
        documentId={documentId}
        onOpenAtLocation={onOpenAtLocation}
        onClose={() => setSelectedStage(null)}
      />
    </>
  );
};

export default DocumentPipelinePanel;


