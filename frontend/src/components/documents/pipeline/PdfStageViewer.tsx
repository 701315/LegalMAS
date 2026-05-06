// =============================================================
// src/components/documents/pipeline/PdfStageViewer.tsx
// =============================================================

import React from "react";
import type { PdfPreviewDTO, PipelineStageViewDTO } from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

/**
 * PdfStageViewer
 *
 * Минималистичный viewer для PDF-артефакта стадии:
 * - если есть inline_url — показывает PDF во встроенном iframe;
 * - если нет — показывает лаконичное сообщение о недоступности встроенного просмотра.
 *
 * Внешние служебные подписи и действия не рендерятся:
 * шапка стадии, режим просмотра и другие метаданные управляются
 * контейнером preview-панели, а не самим viewer-компонентом.
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
  const hasInline = Boolean(inlineUrl);

  if (hasInline && inlineUrl) {
    return (
      <div className="h-full min-h-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] shadow-sm">
        <iframe
          title={`pipeline-stage-${stage.code}`}
          src={inlineUrl}
          className="h-full w-full"
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 text-center">
      <div>
        <p className="text-sm font-medium text-[var(--text-primary)]">
          PDF недоступен для встроенного просмотра
        </p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Для этой стадии не найден inline preview.
        </p>
      </div>
    </div>
  );
};

export default PdfStageViewer;




