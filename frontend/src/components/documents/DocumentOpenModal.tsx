// =============================================================
// src/components/documents/DocumentOpenModal.tsx
// Модалка при клике по документу:
// - показывает название документа
// - даёт выбрать: открыть исходный файл или structured-data
// =============================================================

import React from "react";
import { FileText, ListTree, X } from "lucide-react";
import { useDocumentPdfUrl, useStructuredData } from "../../api/documents";
import type { Document } from "../../types";

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
  // Загружаем URL исходного файла
  const {
    data: pdfData,
    isLoading: isPdfLoading,
    error: pdfError,
  } = useDocumentPdfUrl(doc.id);

  // Загружаем structured-data "по требованию" — включаем запрос только при нажатии кнопки
  // В твоём API useStructuredData(docId) уже сам включает запрос по docId,
  // поэтому чтобы не дёргать его сразу, можно добавить локальный флаг.
  const [loadStructured, setLoadStructured] = React.useState(false);
  const {
    data: structuredData,
    isLoading: isStructuredLoading,
    error: structuredError,
  } = useStructuredData(loadStructured ? doc.id : null);

  const handleOpenPdf = () => {
    // Если ещё грузится
    if (isPdfLoading) {
      return;
    }

    // Ошибку пока показываем простым alert
    if (pdfError) {
      alert("Исходный файл недоступен или произошла ошибка при загрузке URL.");
      return;
    }

    if (!pdfData?.url) {
      alert("Исходный файл недоступен.");
      return;
    }

    // Открываем в новой вкладке
    window.open(pdfData.url, "_blank", "noopener,noreferrer");
  };

  const handleLoadStructured = () => {
    // Просто включаем флаг, чтобы useStructuredData получил doc.id
    setLoadStructured(true);
  };

  const renderStructuredBlock = () => {
    if (!loadStructured) {
      return (
        <button
          type="button"
          onClick={handleLoadStructured}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-gray-300 rounded text-sm text-gray-700 hover:bg-gray-50"
        >
          <ListTree size={16} />
          Просмотреть structured-data
        </button>
      );
    }

    if (isStructuredLoading) {
      return (
        <div className="text-xs text-gray-500 mt-2">
          Загружаем structured-data…
        </div>
      );
    }

    if (structuredError) {
      const err = structuredError as any;
      const status = err?.status;
      const detail = err?.detail || "Ошибка при загрузке structured-data.";

      if (status === 404) {
        return (
          <div className="mt-2 text-xs text-gray-500">
            Структурированные данные для этого документа ещё не сформированы
            или недоступны.
          </div>
        );
      }

      return (
        <div className="mt-2 text-xs text-red-600">
          {String(detail)}
        </div>
      );
    }

    if (!structuredData || structuredData.extracted_values.length === 0) {
      return (
        <div className="mt-2 text-xs text-gray-500">
          Структурированные данные находятся в обработке или недоступны.
        </div>
      );
    }

    return (
      <div className="mt-3 max-h-40 overflow-y-auto border border-gray-100 rounded p-2 bg-gray-50">
        <p className="text-xs text-gray-500 mb-1">
          Краткий список полей (structured-data):
        </p>
        {structuredData.extracted_values.map((val, idx) => (
          <div
            key={idx}
            className="flex justify-between text-[11px] py-0.5 border-b border-gray-100 last:border-0"
          >
            <span className="text-gray-400">
              {val.field_name.replace(/_/g, " ")}
            </span>
            <span className="text-gray-800 font-medium text-right">
              {val.field_value}
            </span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-md mx-4 relative">
        {/* Заголовок */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <h3 className="text-sm font-semibold text-gray-900">
            Документ: {doc.filename}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="Закрыть"
          >
            <X size={16} />
          </button>
        </div>

        {/* Содержимое */}
        <div className="p-4 space-y-3 text-sm">
          <p className="text-xs text-gray-500">
            Выберите действие для документа.
          </p>

          {/* Кнопка: открыть PDF */}
          <button
            type="button"
            onClick={handleOpenPdf}
            disabled={isPdfLoading}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            <FileText size={16} />
            {isPdfLoading ? "Загружаем ссылку на PDF…" : "Открыть исходный файл (PDF)"}
          </button>

          {/* Блок structured-data */}
          {renderStructuredBlock()}
        </div>

        {/* Подвал */}
        <div className="px-4 py-3 border-t flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs border border-gray-300 rounded text-gray-700 hover:bg-gray-50"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

export default DocumentOpenModal;
