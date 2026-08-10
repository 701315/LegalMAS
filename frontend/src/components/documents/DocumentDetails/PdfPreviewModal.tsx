// =============================================================
// PdfPreviewModal.tsx
// Встроенная модалка просмотра PDF для документа.
//
// Архитектура:
// - получает documentId и filename
// - при открытии делает authenticated fetch через axios
// - создаёт blob: URL для iframe
// - MinIO не доступен браузеру напрямую
// - Authorization header подставляется axios interceptor-ом
// =============================================================

import React, { useEffect, useState } from "react";
import { Download, X, Loader2, AlertTriangle } from "lucide-react";
import Button from "../../ui/Button";
import client from "../../../api/client";

interface PdfPreviewModalProps {
  open: boolean;
  documentId: string | null;
  filename: string;
  isDownloading: boolean;
  onDownload: () => void;
  onClose: () => void;
}

export const PdfPreviewModal: React.FC<PdfPreviewModalProps> = ({
  open,
  documentId,
  filename,
  isDownloading,
  onDownload,
  onClose,
}) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !documentId) {
      setBlobUrl(null);
      setLoadError(null);
      setIsLoading(false);
      return;
    }

    let revoked = false;
    let currentBlobUrl: string | null = null;

    const load = async () => {
      setIsLoading(true);
      setLoadError(null);
      setBlobUrl(null);

      try {
        // Authenticated fetch через axios — Authorization header добавляется
        // автоматически request interceptor-ом из client.ts
        const response = await client.get<Blob>(
          `/api/v1/documents/${documentId}/converted-pdf-content`,
          { responseType: "blob" },
        );

        if (revoked) return;

        currentBlobUrl = URL.createObjectURL(response.data);
        setBlobUrl(currentBlobUrl);
      } catch (e) {
        if (revoked) return;
        const msg =
          e instanceof Error ? e.message : "Не удалось загрузить PDF";
        setLoadError(msg);
      } finally {
        if (!revoked) setIsLoading(false);
      }
    };

    void load();

    return () => {
      revoked = true;
      // Освобождаем blob: URL при закрытии или смене документа
      if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl);
      }
    };
  }, [open, documentId]);

  if (!open) return null;

  const handleBackdropClick = (
    event: React.MouseEvent<HTMLDivElement, MouseEvent>,
  ) => {
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-[2px] p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Просмотр файла ${filename}`}
      onClick={handleBackdropClick}
    >
      <div className="flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-4 py-3">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.14em] text-[var(--text-faint)]">
              Original file preview
            </p>
            <h3 className="truncate text-base font-semibold text-[var(--text-primary)]">
              {filename}
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onDownload}
              leftIcon={<Download size={14} />}
              isLoading={isDownloading}
              disabled={isDownloading}
            >
              Скачать оригинал файла
            </Button>

            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onClose}
              aria-label="Закрыть просмотр файла"
            >
              <X size={16} />
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 bg-[var(--bg-subtle)] p-3">
          <div className="h-full overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)]">
            {isLoading && (
              <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
                <Loader2 className="mr-2 animate-spin" size={18} />
                Загрузка файла…
              </div>
            )}

            {loadError && !isLoading && (
              <div className="flex h-full flex-col items-center justify-center px-4 text-center">
                <AlertTriangle
                  size={18}
                  className="mb-1 text-[var(--color-error-text)]"
                />
                <p className="text-xs font-medium text-[var(--color-error-text)]">
                  Не удалось загрузить файл
                </p>
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                  {loadError}
                </p>
              </div>
            )}

            {!isLoading && !loadError && blobUrl && (
              <iframe
                src={blobUrl}
                title={`Просмотр файла ${filename}`}
                className="h-full w-full"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
