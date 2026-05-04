// =============================================================
// src/components/documents/pipeline/PdfStageViewer.tsx
// =============================================================

import React from "react";
import { ExternalLink, FileText } from "lucide-react";
import type { PdfPreviewDTO, PipelineStageViewDTO } from "../../../types";
import Button from "../../ui/Button";

interface Props {
  stage: PipelineStageViewDTO;
}

/**
 * PdfStageViewer
 *
 * Показывает PDF-артефакт стадии:
 * - если есть inline_url — в iframe;
 * - если нет — сообщение, что встроенный просмотр недоступен;
 * - всегда оставляет действие "Открыть в новой вкладке", если есть download_url.
 *
 * Название/описание стадии рендерятся в шапке модалки,
 * поэтому здесь они не дублируются.
 */
export const PdfStageViewer: React.FC<Props> = ({ stage }) => {
  const preview = stage.preview as PdfPreviewDTO | null | undefined;

  if (!preview) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)] shadow-sm">
        PDF-превью недоступно.
      </div>
    );
  }

  const inlineUrl = preview.inline_url ?? undefined;
  const downloadUrl = preview.download_url ?? undefined;
  const hasInline = Boolean(inlineUrl);
  const hasDownload = Boolean(downloadUrl);

  const handleOpenInNewTab = () => {
    if (!downloadUrl) return;
    window.open(downloadUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <FileText size={14} className="shrink-0 text-[var(--text-faint)]" />
          <span>Исходный PDF этого этапа.</span>
        </div>

        {hasDownload && (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={handleOpenInNewTab}
            className="inline-flex items-center gap-1.5"
          >
            <ExternalLink size={13} aria-hidden="true" />
            <span>Открыть в новой вкладке</span>
            <span className="sr-only">(откроется в новой вкладке)</span>
          </Button>
        )}
      </div>

      {hasInline ? (
        <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] shadow-sm">
          <iframe
            title={`pipeline-stage-${stage.code}`}
            src={inlineUrl}
            className="h-full w-full"
          />
        </div>
      ) : (
        <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 text-center">
          <div>
            <p className="text-sm font-medium text-[var(--text-primary)]">
              PDF недоступен для встроенного просмотра
            </p>
            {hasDownload && (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Вы всё ещё можете открыть исходный файл по кнопке выше.
              </p>
            )}
            {!hasDownload && (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Для этой стадии не найдено URL для скачивания PDF-артефакта.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PdfStageViewer;


