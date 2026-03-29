// =============================================================
// src/components/viewer/DocumentViewerModal.tsx
// Модалка с PDF‑viewer для договора.
// - Показывает PDF по URL
// - Умеет прыгать на нужную страницу
// - Вызывается через OpenViewerAtFn из GridTab / EvidencePanel / DDGrid
// =============================================================

import React from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { OpenViewerAtPayload } from "../../types";

// ВАЖНО: путь именно до pdf.worker.min.mjs из pdfjs-dist
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface DocumentViewerModalProps {
  open: boolean;
  onClose: () => void;

  // Прямой URL до сконвертированного PDF.
  fileUrl: string | null;

  // Куда именно нужно «прыгнуть»
  location: OpenViewerAtPayload | null;

  // Необязательный первичный зум (в долях ширины контейнера)
  initialScale?: number;

  // Заголовок: имя документа ИЛИ текст ошибки/статуса (из GridTab)
  title?: string | null;
}

const DocumentViewerModal: React.FC<DocumentViewerModalProps> = ({
  open,
  onClose,
  fileUrl,
  location,
  initialScale = 0.9,
  title,
}) => {
  const [numPages, setNumPages] = React.useState<number | null>(null);
  const [pageNumber, setPageNumber] = React.useState<number>(1);
  const containerRef = React.useRef<HTMLDivElement | null>(null);

  // Ширина контейнера, считанная один раз и при ресайзах
  const [containerWidth, setContainerWidth] = React.useState<number | null>(
    null,
  );

  // При смене location — прыгаем на нужную страницу
  React.useEffect(() => {
    if (location?.page && location.page > 0) {
      setPageNumber(location.page);
    }
  }, [location]);

  // Измеряем ширину контейнера и подписываемся на resize
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

  // Esc‑закрытие
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

  const handlePrevPage = () => {
    setPageNumber((prev) => Math.max(1, prev - 1));
  };

  const handleNextPage = () => {
    setPageNumber((prev) =>
      numPages ? Math.min(numPages, prev + 1) : prev,
    );
  };

  const headerTitle =
    title ||
    (location?.documentId ? `Документ ${location.documentId}` : "Документ");

  const hasErrorTitle = Boolean(title && title.toLowerCase().includes("ошибка"));
  const isLoadingTitle = Boolean(
    title && title.toLowerCase().includes("загрузка"),
  );

  // Итоговая ширина страницы: либо измеренная, либо дефолт
  const pageWidth = (containerWidth ?? 900) * initialScale;

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60"
      onClick={handleBackdropClick}
    >
      <div
        className="bg-white rounded-lg shadow-2xl w-[95vw] h-[95vh] max-w-6xl flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-label="Просмотр документа"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b text-xs">
          <div className="flex flex-col">
            <span
              className={
                "truncate max-w-[360px] " +
                (hasErrorTitle
                  ? "font-medium text-red-600"
                  : isLoadingTitle
                  ? "font-medium text-gray-600"
                  : "font-medium text-gray-800")
              }
            >
              {headerTitle}
            </span>
            <span className="text-[11px] text-gray-500">
              {location?.page ? `Страница ${location.page}` : "Страница 1"}
              {location?.clauseUid && ` · Клауза ${location.clauseUid}`}
            </span>
          </div>
          <button
            type="button"
            className="px-2 py-1 border rounded text-xs hover:bg-gray-50"
            onClick={onClose}
          >
            Закрыть
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 text-[11px] text-gray-600">
          <div className="flex items-center gap-2">
            <span>Навигация:</span>
            <button
              type="button"
              className="px-2 py-1 border rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white"
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
              className="px-2 py-1 border rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white"
              onClick={handleNextPage}
              disabled={!numPages || pageNumber >= numPages}
            >
              ▶
            </button>
          </div>
          <div className="text-[11px] text-gray-400">
            Нажмите Esc или «Закрыть», чтобы выйти
          </div>
        </div>

        {/* Body */}
        <div
          ref={containerRef}
          className="flex-1 overflow-auto bg-gray-200 flex items-center justify-center"
        >
          {!fileUrl ? (
            <div className="text-xs text-red-600 px-4 py-2 bg-white rounded">
              Не удалось получить ссылку на PDF.
            </div>
          ) : (
            <div className="bg-gray-400/10 p-2">
              <Document
                file={fileUrl}
                onLoadSuccess={handleDocumentLoad}
                loading={
                  <div className="text-xs text-gray-600 px-4 py-2 bg-white rounded">
                    Загружаем PDF…
                  </div>
                }
                error={
                  <div className="text-xs text-red-600 px-4 py-2 bg-white rounded">
                    Не удалось загрузить PDF.
                  </div>
                }
              >
                <Page pageNumber={pageNumber} width={pageWidth} />
              </Document>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DocumentViewerModal;
