// =============================================================
// src/components/documents/pipeline/DocumentPipelinePanel.tsx
// =============================================================

import React from "react";
import {
  ArrowRight,
  Loader2,
  AlertTriangle,
  GitBranch,
} from "lucide-react";
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
        const result = await getDocumentPipelineView(
          documentId,
          controller.signal,
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
  }, [documentId]);

  const hasStages = !!data && data.stages.length > 0;

  return (
    <>
      <div className="space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
              <GitBranch size={13} className="shrink-0" />
              <span>Document pipeline</span>
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              SOURCE <ArrowRight className="inline h-3 w-3" /> PRIMARY{" "}
              <ArrowRight className="inline h-3 w-3" /> EXTRACT{" "}
              <ArrowRight className="inline h-3 w-3" /> PII{" "}
              <ArrowRight className="inline h-3 w-3" /> STRUCTURE{" "}
              <ArrowRight className="inline h-3 w-3" /> CHUNKS
            </p>
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">
              Путь документа по стадиям обработки — от исходного PDF до
              структуры и чанков.
            </p>
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-2 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-sm text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--text-faint)]" />
            <span>Загрузка стадий обработки…</span>
          </div>
        )}

        {!loading && error && (
          <div className="flex items-start gap-2 rounded-2xl border border-[var(--color-error-soft-border)] bg-[var(--color-error-soft-bg)] px-3 py-2 text-sm text-[var(--color-error-strong)]">
            <AlertTriangle className="mt-[2px] h-4 w-4 shrink-0 text-[var(--color-error)]" />
            <span>{error}</span>
          </div>
        )}

        {!loading && !error && hasStages && (
          <div className="space-y-1.5">
            {data!.stages.map((stage) => (
              <PipelineStageRow
                key={stage.code}
                stage={stage}
                onOpen={setSelectedStage}
              />
            ))}
          </div>
        )}

        {!loading && !error && data && data.stages.length === 0 && (
          <div className="flex items-center justify-between rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-2 text-sm text-[var(--text-muted)]">
            <span>Стадии обработки пока недоступны.</span>
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

