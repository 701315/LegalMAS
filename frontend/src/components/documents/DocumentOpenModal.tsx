// =============================================================
// src/components/documents/DocumentOpenModal.tsx
// Модалка при клике по документу:
// - показывает название документа
// - даёт выбрать: открыть исходный файл или structured-data
// =============================================================

import React from "react";
import { FileText, ListTree, X } from "lucide-react";
import { useDocumentPdfUrl, useStructuredData } from "../../api/documents";
import type { Document, ClauseNode } from "../../types";
import Button from "../ui/Button";

interface DocumentOpenModalProps {
  doc: Document;
  onClose: () => void;
}

/**
 * Простая модалка поверх всей страницы.
 * Не использует порталы, опирается на tailwind-стили проекта.
 */
const DocumentOpenModal: React.FC<DocumentOpenModalProps> = ({
  doc,
  onClose,
}) => {
  const {
    data: pdfData,
    isLoading: isPdfLoading,
    error: pdfError,
  } = useDocumentPdfUrl(doc.id);

  const [loadStructured, setLoadStructured] = React.useState(false);
  const {
    data: structuredData,
    isLoading: isStructuredLoading,
    error: structuredError,
  } = useStructuredData(loadStructured ? doc.id : null);

  const handleOpenPdf = () => {
    if (isPdfLoading) return;

    if (pdfError) {
      // TODO: заменить на нормальный inline-тост, когда будет общий механизм
      alert(
        "Исходный файл недоступен или произошла ошибка при загрузке URL.",
      );
      return;
    }

    if (!pdfData?.url) {
      alert("Исходный файл недоступен.");
      return;
    }

    window.open(pdfData.url, "_blank", "noopener,noreferrer");
  };

  const handleLoadStructured = () => {
    setLoadStructured(true);
  };

  const renderClauseRow = (
    node: ClauseNode,
    key: React.Key,
    indentPx: number,
  ) => (
    <div
      key={key}
      className="flex justify-between border-b border-[var(--border-subtle)] py-0.5 text-[11px]"
      style={{ paddingLeft: indentPx }}
    >
      <span className="text-[var(--text-faint)]">{node.clause_uid}</span>
      <span className="text-right font-medium text-[var(--text-primary)]">
        {node.title}
      </span>
    </div>
  );

  const renderClauseTree = (
    nodes: ClauseNode[] | undefined | null,
    indentPx = 0,
    maxRows = 80,
    acc: React.ReactNode[] = [],
  ): React.ReactNode[] => {
    if (!nodes || !Array.isArray(nodes) || acc.length >= maxRows) {
      return acc;
    }

    for (const node of nodes) {
      if (!node || acc.length >= maxRows) break;

      const key = `${node.clause_uid}-${node.start_page}-${acc.length}`;
      acc.push(renderClauseRow(node, key, indentPx));

      if (Array.isArray(node.children) && node.children.length > 0) {
        renderClauseTree(node.children, indentPx + 12, maxRows, acc);
      }
    }

    return acc;
  };

  const renderStructuredBlock = () => {
    if (!loadStructured) {
      return (
        <Button
          type="button"
          variant="secondary"
          size="md"
          onClick={handleLoadStructured}
          className="w-full justify-center gap-2"
        >
          <ListTree size={16} />
          Просмотреть structured-data
        </Button>
      );
    }

    if (isStructuredLoading) {
      return (
        <div className="mt-2 text-xs text-[var(--text-muted)]">
          Загружаем structured-data…
        </div>
      );
    }

    if (structuredError) {
      const err = structuredError as unknown;

      const status =
        typeof err === "object" && err !== null
          ? (err as { status?: number }).status
          : undefined;

      const detailValue =
        typeof err === "object" && err !== null
          ? (err as { detail?: unknown }).detail
          : undefined;

      const messageValue =
        typeof err === "object" && err !== null
          ? (err as { message?: string }).message
          : undefined;

      const detailMessage =
        typeof detailValue === "string"
          ? detailValue
          : typeof messageValue === "string"
            ? messageValue
            : "Ошибка при загрузке structured-data.";

      if (status === 404) {
        return (
          <div className="mt-2 text-xs text-[var(--text-muted)]">
            Структурированные данные для этого документа ещё не сформированы
            или недоступны.
          </div>
        );
      }

      return (
        <div className="mt-2 text-xs text-[var(--color-error)]">
          {String(detailMessage)}
        </div>
      );
    }

    if (
      !structuredData ||
      !Array.isArray(structuredData) ||
      structuredData.length === 0
    ) {
      return (
        <div className="mt-2 text-xs text-[var(--text-muted)]">
          Структурированные данные находятся в обработке или недоступны.
        </div>
      );
    }

    const rows = renderClauseTree(structuredData);

    return (
      <div className="mt-3 max-h-40 overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2">
        <p className="mb-1 text-xs text-[var(--text-muted)]">
          Краткое оглавление (structured-data):
        </p>
        {rows}
      </div>
    );
  };

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/45 px-4"
      onClick={handleBackdropClick}
    >
      <div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        {/* Заголовок */}
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
          <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">
            Документ: {doc.filename}
          </h3>
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

        {/* Содержимое */}
        <div className="space-y-3 px-4 py-4 text-sm">
          <p className="text-xs text-[var(--text-muted)]">
            Выберите действие для документа.
          </p>

          <Button
            type="button"
            variant="primary"
            size="md"
            onClick={handleOpenPdf}
            disabled={isPdfLoading}
            className="w-full justify-center gap-2"
          >
            <FileText size={16} />
            {isPdfLoading
              ? "Загружаем ссылку на PDF…"
              : "Открыть исходный файл (PDF)"}
          </Button>

          {renderStructuredBlock()}
        </div>

        {/* Подвал */}
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

export default DocumentOpenModal;


