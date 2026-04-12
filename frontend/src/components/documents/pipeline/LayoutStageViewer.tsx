import React from "react";
import type { LayoutPreviewDTO, PipelineStageViewDTO } from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

/**
 * LayoutStageViewer
 *
 * Показывает layout-артефакт в двух вкладках:
 * - Просмотр: страницы и извлечённый текст;
 * - JSON: сырой payload артефакта.
 *
 * Название и описание стадии уже показаны в шапке модалки,
 * поэтому здесь мы не дублируем их повторно.
 */
export const LayoutStageViewer: React.FC<Props> = ({ stage }) => {
  const preview = stage.preview as LayoutPreviewDTO | null | undefined;
  const [tab, setTab] = React.useState<"view" | "json">("view");

  if (!preview) {
    return (
      <div className="text-sm text-gray-500">
        Layout-превью недоступно.
      </div>
    );
  }

  const jsonText = JSON.stringify(preview.raw_json ?? null, null, 2);

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setTab("view")}
          className={`px-3 py-1.5 rounded text-xs border ${
            tab === "view"
              ? "bg-blue-600 text-white border-blue-600"
              : "bg-white text-gray-700 border-gray-200"
          }`}
        >
          Просмотр
        </button>

        <button
          type="button"
          onClick={() => setTab("json")}
          className={`px-3 py-1.5 rounded text-xs border ${
            tab === "json"
              ? "bg-blue-600 text-white border-blue-600"
              : "bg-white text-gray-700 border-gray-200"
          }`}
        >
          JSON
        </button>
      </div>

      {tab === "view" ? (
        <div className="flex-1 overflow-y-auto space-y-3">
          {preview.pages.length > 0 ? (
            preview.pages.map((page) => (
              <div
                key={page.page}
                className="border border-gray-100 rounded-lg p-3 bg-gray-50"
              >
                <div className="flex items-center justify-between gap-3 mb-2">
                  <p className="text-sm font-medium text-gray-800">
                    Страница {page.page}
                  </p>
                  <p className="text-[11px] text-gray-400">
                    Элементов: {page.element_count}
                  </p>
                </div>

                <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-gray-700 font-sans">
                  {page.text || "—"}
                </pre>
              </div>
            ))
          ) : (
            <div className="text-sm text-gray-500">
              Нет страниц для отображения.
            </div>
          )}
        </div>
      ) : (
        <pre className="flex-1 overflow-auto text-xs leading-5 bg-gray-900 text-gray-100 rounded-lg p-4">
          {jsonText}
        </pre>
      )}
    </div>
  );
};

export default LayoutStageViewer;

