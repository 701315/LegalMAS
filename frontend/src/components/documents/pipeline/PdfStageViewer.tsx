// =============================================================
// src/components/documents/pipeline/PdfStageViewer.tsx
// =============================================================

import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, AlertTriangle } from "lucide-react";
import type { PdfPreviewDTO, PipelineStageViewDTO } from "../../../types";
import client from "../../../api/client";

interface Props {
  stage: PipelineStageViewDTO;
}

/**
 * PdfStageViewer
 *
 * Browser-safe PDF viewer для pipeline stage:
 * - inline_url больше не отдаётся напрямую в iframe;
 * - сначала делаем authenticated GET через axios client;
 * - axios interceptor добавляет Authorization: Bearer;
 * - затем создаём blob: URL и уже его отдаём в iframe.
 *
 * Это совместимо с приватным MinIO и bearer-header auth model.
 */
export const PdfStageViewer: React.FC<Props> = ({ stage }) => {
  const { t } = useTranslation("pipeline");
  const preview = stage.preview as PdfPreviewDTO | null | undefined;
  const inlineUrl = preview?.inline_url ?? null;

  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!inlineUrl) {
      setBlobUrl(null);
      setLoadError(null);
      setIsLoading(false);
      return;
    }

    let disposed = false;
    let currentBlobUrl: string | null = null;

    const load = async () => {
      setIsLoading(true);
      setLoadError(null);
      setBlobUrl(null);

      try {
        const response = await client.get<Blob>(inlineUrl, {
          responseType: "blob",
        });

        if (disposed) return;

        currentBlobUrl = URL.createObjectURL(response.data);
        setBlobUrl(currentBlobUrl);
      } catch (e) {
        if (disposed) return;
        const msg =
          e instanceof Error ? e.message : t("pdfViewer.loadError");
        setLoadError(msg);
      } finally {
        if (!disposed) {
          setIsLoading(false);
        }
      }
    };

    void load();

    return () => {
      disposed = true;
      if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl);
      }
    };
  }, [inlineUrl, t]);

  if (!preview) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)] shadow-sm">
        {t("pdfViewer.unavailable")}
      </div>
    );
  }

  if (!inlineUrl) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 text-center">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {t("pdfViewer.notAvailableEmbedded")}
          </p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            {t("pdfViewer.noInlinePreview")}
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 text-sm text-[var(--text-muted)] shadow-sm">
        <Loader2 className="mr-2 animate-spin" size={18} />
        {t("pdfViewer.loading")}
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 text-center shadow-sm">
        <div>
          <AlertTriangle
            size={18}
            className="mx-auto mb-2 text-[var(--color-error-text)]"
          />
          <p className="text-sm font-medium text-[var(--color-error-text)]">
            {t("pdfViewer.loadError")}
          </p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            {loadError}
          </p>
        </div>
      </div>
    );
  }

  if (blobUrl) {
    return (
      <div className="h-full min-h-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] shadow-sm">
        <iframe
          title={`pipeline-stage-${stage.code}`}
          src={blobUrl}
          className="h-full w-full"
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 text-center">
      <div>
        <p className="text-sm font-medium text-[var(--text-primary)]">
          {t("pdfViewer.notAvailableEmbedded")}
        </p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {t("pdfViewer.noInlinePreview")}
        </p>
      </div>
    </div>
  );
};

export default PdfStageViewer;


