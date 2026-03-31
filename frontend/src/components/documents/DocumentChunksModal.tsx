// =============================================================
// src/components/documents/DocumentChunksModal.tsx
// Модалка для просмотра документа в виде чанков (Markdown).
//
// Для непрофессионального пользователя:
// - показывает специальный файл, где документ разбит на чанки,
//   так как его «видит» система чанкинга;
// - помогает глазами проверить границы чанков и структуру.
// =============================================================

import React, { useEffect, useState } from "react";
import { X, Loader2, AlertTriangle } from "lucide-react";

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[95vh] flex flex-col">
        {/* header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-gray-900 truncate">
              Документ в формате чанков
            </h2>
            <p className="text-xs text-gray-500 truncate" title={docName}>
              {docName}
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 text-gray-500"
          >
            <X size={16} />
          </button>
        </div>

        {/* пояснение */}
        <div className="px-4 pt-2 text-[11px] text-gray-500 border-b pb-2">
          Этот просмотр показывает документ так, как его «видит» система
          чанкинга: один чанк за другим, с заголовками и служебной
          информацией. Прокрутите вниз, чтобы увидеть весь документ.
        </div>

        {/* body */}
        <div className="flex-1 p-4">
          {isLoading && (
            <div className="h-[70vh] flex items-center justify-center text-gray-400 text-sm">
              <Loader2 className="animate-spin mr-2" size={18} />
              Загрузка файла чанков…
            </div>
          )}

          {loadError && !isLoading && (
            <div className="h-[70vh] flex flex-col items-center justify-center text-center text-xs text-red-700">
              <AlertTriangle size={18} className="mb-1 text-red-500" />
              <p>Ошибка при загрузке файла чанков</p>
              <p className="mt-1 text-[11px] text-gray-500 break-words">
                {loadError}
              </p>
            </div>
          )}

          {!isLoading && !loadError && content && (
            <div className="h-[70vh] border rounded bg-gray-50 overflow-y-auto text-xs">
              <pre className="p-3 whitespace-pre-wrap text-[11px] leading-snug font-mono">
                {content}
              </pre>
            </div>
          )}

          {!isLoading && !loadError && !content && (
            <div className="h-[70vh] flex items-center justify-center text-xs text-gray-500">
              Нет данных для отображения чанков документа.
            </div>
          )}
        </div>

        {/* footer */}
        <div className="px-4 py-2 border-t flex justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs rounded border text-gray-700 hover:bg-gray-50"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

export default DocumentChunksModal;
