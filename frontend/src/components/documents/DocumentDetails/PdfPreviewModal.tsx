// =============================================================
// PdfPreviewModal.tsx
// Встроенная модалка просмотра PDF для документа.
// Используется внутри DocumentDetails.
// =============================================================

import React from "react";
import { Download, X } from "lucide-react";
import Button from "../../ui/Button";

interface PdfPreviewModalProps {
  open: boolean;
  pdfUrl: string | null;
  filename: string;
  isDownloading: boolean;
  onDownload: () => void;
  onClose: () => void;
}

export const PdfPreviewModal: React.FC<PdfPreviewModalProps> = ({
  open,
  pdfUrl,
  filename,
  isDownloading,
  onDownload,
  onClose,
}) => {
  if (!open || !pdfUrl) return null;

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
            <iframe
              src={pdfUrl}
              title={`Просмотр файла ${filename}`}
              className="h-full w-full"
            />
          </div>
        </div>
      </div>
    </div>
  );
};

