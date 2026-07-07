// src/components/viewer/DocumentViewerModal.tsx

import React from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { OpenViewerAtPayload } from "../../types";

// ВАЖНО: путь именно до pdf.worker.min.mjs из pdfjs-dist
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export interface LayoutElement {
  elementId: string;
  page: number;
  bbox: [number, number, number, number];
}

export interface SizedChunkMeta {
  id: string;
  elementIds: string[];
  clauseUids: string[];
}

interface DocumentViewerModalProps {
  open: boolean;
  onClose: () => void;
  fileUrl: string | null;
  location: OpenViewerAtPayload | null;
  initialScale?: number;
  title?: string | null;
  layoutElements?: LayoutElement[];
  sizedChunks?: SizedChunkMeta[];
}

const DocumentViewerModal: React.FC<DocumentViewerModalProps> = ({
  open,
  onClose,
  fileUrl,
  location,
  initialScale = 0.9,
  title,
  layoutElements,
  sizedChunks,
}) => {
  const [numPages, setNumPages] = React.useState<number | null>(null);
  const [pageNumber, setPageNumber] = React.useState<number>(1);
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = React.useState<number | null>(
    null,
  );
  const [pageSize, setPageSize] = React.useState<{
    originalWidth: number;
    originalHeight: number;
  } | null>(null);

  React.useEffect(() => {
    if (location?.page && location.page > 0) {
      setPageNumber(location.page);
    }
  }, [location]);

  // Автоскролл к началу страницы при её смене.
  // Если у нас есть layout и активный фрагмент — скроллим к нему,
  // иначе просто скроллим в самый верх, чтобы верх страницы был виден.
  React.useEffect(() => {
    if (!open || !containerRef.current) return;

    // Небольшая задержка — ждём рендер новой страницы PDF
    const timeoutId = window.setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      container.scrollTop = 0;
    }, 100);

    return () => window.clearTimeout(timeoutId);
  }, [open, pageNumber, fileUrl]);

  React.useLayoutEffect(() => {
    if (!open) return;

    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.clientWidth);
      }
    };

    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => {
      window.removeEventListener("resize", updateWidth);
    };
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleDocumentLoad = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    if (!location?.page || location.page < 1 || location.page > numPages) {
      setPageNumber(1);
    }
  };

  type PageRenderInfo = {
    originalWidth?: number;
    originalHeight?: number;
  };

  const handlePageRenderSuccess = (pageData: PageRenderInfo) => {
    if (
      typeof pageData.originalWidth === "number" &&
      typeof pageData.originalHeight === "number"
    ) {
      setPageSize({
        originalWidth: pageData.originalWidth,
        originalHeight: pageData.originalHeight,
      });
    }

    // После рендера страницы — если есть активный фрагмент с bbox,
    // скроллим контейнер так, чтобы фрагмент был виден с небольшим
    // offset сверху (для визуального контекста).
    window.setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      // Ищем активный overlay на текущей странице
      const activeOverlay = container.querySelector<HTMLDivElement>(
        '[data-active-overlay="true"]',
      );

      if (activeOverlay) {
        // Скроллим так, чтобы активный элемент был в верхней трети экрана
        const containerRect = container.getBoundingClientRect();
        const overlayRect = activeOverlay.getBoundingClientRect();
        const offsetFromTop = overlayRect.top - containerRect.top;
        const desiredOffset = containerRect.height * 0.15; // 15% от высоты сверху
        container.scrollTop += offsetFromTop - desiredOffset;
      } else {
        // Если активного фрагмента нет — просто в самый верх страницы
        container.scrollTop = 0;
      }
    }, 150);
  };

  const handlePrevPage = () => {
    setPageNumber((prev) => Math.max(1, prev - 1));
  };

  const handleNextPage = () => {
    setPageNumber((prev) => (numPages ? Math.min(numPages, prev + 1) : prev));
  };

  const headerTitle =
    title ||
    (location?.documentId ? `Документ ${location.documentId}` : "Документ");

  const hasErrorTitle = Boolean(
    title && title.toLowerCase().includes("ошибка"),
  );
  const isLoadingTitle = Boolean(
    title && title.toLowerCase().includes("загрузка"),
  );

  const pageWidth = (containerWidth ?? 900) * initialScale;

  let activeChunkIndex = -1;

  if (sizedChunks && sizedChunks.length > 0 && location) {
    const { chunkId, chunkIndex, clauseUid } = location;

    if (chunkId) {
      const idx = sizedChunks.findIndex((ch) => ch.id === chunkId);
      if (idx >= 0) {
        activeChunkIndex = idx;
      }
    }

    if (
      activeChunkIndex < 0 &&
      typeof chunkIndex === "number" &&
      chunkIndex >= 0 &&
      chunkIndex < sizedChunks.length
    ) {
      activeChunkIndex = chunkIndex;
    }

    if (activeChunkIndex < 0 && clauseUid) {
      const idx = sizedChunks.findIndex((ch) =>
        ch.clauseUids?.includes(clauseUid),
      );
      if (idx >= 0) {
        activeChunkIndex = idx;
      }
    }
  }

  const elementToChunkIndex = (() => {
    const map = new Map<string, number>();
    (sizedChunks ?? []).forEach((chunk, chunkIndex) => {
      (chunk.elementIds ?? []).forEach((elId) => {
        if (elId) {
          map.set(elId, chunkIndex);
        }
      });
    });
    return map;
  })();

  const pageOverlays: {
    bbox: [number, number, number, number];
    chunkIndex: number | null;
  }[] =
    layoutElements && layoutElements.length
      ? layoutElements
          .filter((el) => el.page === pageNumber)
          .map((el) => ({
            bbox: el.bbox,
            chunkIndex: elementToChunkIndex.get(el.elementId) ?? null,
          }))
      : [];

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/65"
      onClick={handleBackdropClick}
    >
      <div
        className="flex h-[95vh] w-[95vw] max-w-6xl flex-col rounded-[28px] border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Просмотр документа"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border-soft)] px-4 py-2 text-xs">
          <div className="flex flex-col">
            <span
              className={
                "max-w-[360px] truncate " +
                (hasErrorTitle
                  ? "font-medium text-[color:rgb(161,53,68)]"
                  : isLoadingTitle
                  ? "font-medium text-[var(--text-secondary)]"
                  : "font-medium text-[var(--text-primary)]")
              }
            >
              {headerTitle}
            </span>
            <span className="text-[11px] text-[var(--text-muted)]">
              {location?.page ? `Страница ${location.page}` : "Страница 1"}
              {location?.clauseUid && ` · Клауза ${location.clauseUid}`}
            </span>
          </div>
          <button
            type="button"
            className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-3 py-1 text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
            onClick={onClose}
          >
            Закрыть
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-2 text-[11px] text-[var(--text-secondary)]">
          <div className="flex items-center gap-2">
            <span>Навигация:</span>
            <button
              type="button"
              className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-1 hover:bg-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-40"
              onClick={handlePrevPage}
              disabled={pageNumber <= 1}
            >
              ◀
            </button>
            <span>
              Стр. {pageNumber}
              {numPages ? ` из ${numPages}` : ""}
            </span>
            <button
              type="button"
              className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-1 hover:bg-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-40"
              onClick={handleNextPage}
              disabled={!numPages || pageNumber >= numPages}
            >
              ▶
            </button>
          </div>
          <div className="text-[11px] text-[var(--text-muted)]">
            Esc или «Закрыть», чтобы выйти
          </div>
        </div>

        {/* Body */}
        <div
          ref={containerRef}
          className="flex flex-1 justify-center overflow-auto bg-[var(--bg-base)] p-3"
        >
          {!fileUrl ? (
            <div className="rounded-[16px] bg-[var(--bg-card)] px-4 py-3 text-xs text-[color:rgb(161,53,68)]">
              Не удалось получить ссылку на PDF.
            </div>
          ) : (
            <div className="bg-[var(--bg-elevated-soft)]">
              <Document
                file={fileUrl}
                onLoadSuccess={handleDocumentLoad}
                loading={
                  <div className="rounded-[16px] bg-[var(--bg-card)] px-4 py-3 text-xs text-[var(--text-secondary)]">
                    Загружаем PDF…
                  </div>
                }
                error={
                  <div className="rounded-[16px] bg-[var(--bg-card)] px-4 py-3 text-xs text-[color:rgb(161,53,68)]">
                    Не удалось загрузить PDF.
                  </div>
                }
              >
                <div className="relative" style={{ width: pageWidth }}>
                  <Page
                    pageNumber={pageNumber}
                    width={pageWidth}
                    onRenderSuccess={handlePageRenderSuccess}
                  />

                  {pageOverlays.length > 0 && (
                    <div className="pointer-events-none absolute inset-0">
                      {pageOverlays.map((ov, i) => {
                        if (ov.chunkIndex == null) return null;
                        if (!pageSize) return null;

                        const [x0, top, x1, bottom] = ov.bbox;

                        const scaleX = pageWidth / pageSize.originalWidth;
                        const scaleY = scaleX;

                        const left = x0 * scaleX;
                        const width = (x1 - x0) * scaleX;
                        const y = top * scaleY;
                        const height = (bottom - top) * scaleY;

                        const isEven = ov.chunkIndex % 2 === 0;
                        const isActive =
                          activeChunkIndex >= 0 &&
                          ov.chunkIndex === activeChunkIndex;

                        const bgClass = isActive
                          ? "bg-[var(--accent-primary)]/18 ring-2 ring-[var(--accent-primary)]/80"
                          : isEven
                          ? "bg-white/55"
                          : "bg-black/8";

                        return (
                          <div
                            key={i}
                            className={bgClass}
                            data-active-overlay={isActive ? "true" : undefined}
                            style={{
                              position: "absolute",
                              left,
                              top: y,
                              width,
                              height,
                            }}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              </Document>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DocumentViewerModal;

