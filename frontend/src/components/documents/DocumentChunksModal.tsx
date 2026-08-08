// =============================================================
// src/components/documents/DocumentChunksModal.tsx
// Модалка для просмотра документа в виде чанков (Markdown).
// =============================================================

import React, { useEffect, useState } from "react";
import { X, Loader2, AlertTriangle } from "lucide-react";
import Button from "../ui/Button";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  chunkViewUrl: string | null;
  docName: string;
}

export const DocumentChunksModal: React.FC<Props> = ({
  isOpen,
  onClose,
  chunkViewUrl,
  docName,
}) => {
  const [content, setContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !chunkViewUrl) {
      setContent(null);
      setLoadError(null);
      setIsLoading(false);
      return;
    }

    let aborted = false;

    const load = async () => {
      setIsLoading(true);
      setLoadError(null);
      try {
        const resp = await fetch(chunkViewUrl);
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const text = await resp.text();
        if (!aborted) {
          setContent(text);
        }
      } catch (e) {
        if (!aborted) {
          const msg =
            e instanceof Error ? e.message : "Не удалось загрузить файл чанков";
          setLoadError(msg);
        }
      } finally {
        if (!aborted) {
          setIsLoading(false);
        }
      }
    };

    void load();

    return () => {
      aborted = true;
    };
  }, [isOpen, chunkViewUrl]);

  if (!isOpen) return null;

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-4"
      onClick={handleBackdropClick}
    >
      <div className="flex max-h-[95vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        {/* header */}
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-[var(--text-primary)]">
              Документ в формате чанков
            </h2>
            <p
              className="truncate text-xs text-[var(--text-muted)]"
              title={docName}
            >
              {docName}
            </p>
          </div>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Закрыть"
            className="px-2 py-1 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            <X size={16} />
          </Button>
        </div>

        {/* пояснение */}
        <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-2">
          <p className="text-[11px] leading-5 text-[var(--text-muted)]">
            Этот просмотр показывает документ так, как его «видит» система
            чанкинга: один чанк за другим, с заголовками и служебной
            информацией. Прокрутите вниз, чтобы увидеть весь документ.
          </p>
        </div>

        {/* body */}
        <div className="flex-1 p-4">
          {isLoading && (
            <div className="flex h-[70vh] items-center justify-center text-sm text-[var(--text-muted)]">
              <Loader2 className="mr-2 animate-spin" size={18} />
              Загрузка файла чанков…
            </div>
          )}

          {loadError && !isLoading && (
            <div className="flex h-[70vh] flex-col items-center justify-center rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 text-center">
              <AlertTriangle
                size={18}
                className="mb-1 text-[var(--color-error-text)]"
              />
              <p className="text-xs font-medium text-[var(--color-error-text)]">
                Ошибка при загрузке файла чанков
              </p>
              <p className="mt-1 break-words text-[11px] text-[var(--text-muted)]">
                {loadError}
              </p>
            </div>
          )}

          {!isLoading && !loadError && content && (
            <div className="h-[70vh] overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
              <pre className="p-4 font-mono text-[11px] leading-snug whitespace-pre-wrap text-[var(--text-primary)]">
                {content}
              </pre>
            </div>
          )}

          {!isLoading && !loadError && !content && (
            <div className="flex h-[70vh] items-center justify-center rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 text-center">
              <p className="text-xs text-[var(--text-muted)]">
                Нет данных для отображения чанков документа.
              </p>
            </div>
          )}
        </div>

        {/* footer */}
        <div className="flex justify-end border-t border-[var(--border-subtle)] px-4 py-3">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onClose}
          >
            Закрыть
          </Button>
        </div>
      </div>
    </div>
  );
};

export default DocumentChunksModal;


