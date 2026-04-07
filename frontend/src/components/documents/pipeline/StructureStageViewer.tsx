import React from "react";
import type {
  PipelineStageViewDTO,
  StructurePreviewDTO,
  StructureSectionPreviewDTO,
} from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

export const StructureStageViewer: React.FC<Props> = ({ stage }) => {
  const preview = stage.preview as StructurePreviewDTO | null | undefined;
  const [selectedId, setSelectedId] = React.useState<string | null>(
    preview?.sections?.[0]?.id ?? null,
  );

  if (!preview) {
    return (
      <div className="text-sm text-gray-500">
        Structure-превью недоступно.
      </div>
    );
  }

  const selectedSection: StructureSectionPreviewDTO | undefined =
    preview.sections.find((section) => section.id === selectedId);

  return (
    <div className="h-full flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900">{stage.title}</h3>
        <p className="text-xs text-gray-500">{stage.description}</p>
      </div>

      <div className="grid grid-cols-12 gap-4 min-h-[70vh]">
        <div className="col-span-4 border border-gray-100 rounded-lg overflow-hidden bg-white">
          <div className="px-3 py-2 border-b bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Секции
          </div>
          <div className="max-h-[70vh] overflow-y-auto">
            {preview.sections.length > 0 ? (
              preview.sections.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setSelectedId(section.id)}
                  className={`w-full text-left px-3 py-2 border-b border-gray-50 hover:bg-gray-50 ${
                    selectedId === section.id ? "bg-blue-50" : "bg-white"
                  }`}
                  style={{ paddingLeft: `${12 + section.level * 12}px` }}
                >
                  <div className="text-sm text-gray-800 font-medium truncate">
                    {section.title || "Untitled"}
                  </div>
                  <div className="text-[11px] text-gray-400">
                    level {section.level}
                    {(section.page_from || section.page_to) &&
                      ` · стр. ${section.page_from ?? "?"}–${section.page_to ?? "?"}`}
                  </div>
                </button>
              ))
            ) : (
              <div className="p-3 text-sm text-gray-500">Секции отсутствуют.</div>
            )}
          </div>
        </div>

        <div className="col-span-8 border border-gray-100 rounded-lg bg-white p-4">
          {selectedSection ? (
            <div className="space-y-3">
              <div>
                <h4 className="text-base font-semibold text-gray-900">
                  {selectedSection.title || "Untitled"}
                </h4>
                <p className="text-xs text-gray-500 mt-1">
                  Уровень: {selectedSection.level}
                  {(selectedSection.page_from || selectedSection.page_to) &&
                    ` · Страницы: ${selectedSection.page_from ?? "?"}–${selectedSection.page_to ?? "?"}`}
                </p>
              </div>

              <div className="border border-gray-100 rounded-lg p-3 bg-gray-50">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Предпросмотр текста
                </p>
                <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-700 font-sans">
                  {selectedSection.text_preview || "Нет текстового превью."}
                </pre>
              </div>
            </div>
          ) : (
            <div className="text-sm text-gray-500">
              Выбери секцию слева.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StructureStageViewer;


