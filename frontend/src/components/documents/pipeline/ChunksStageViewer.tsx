import React from "react";
import type {
  ChunksPreviewDTO,
  ChunkPreviewDTO,
  PipelineStageViewDTO,
} from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

export const ChunksStageViewer: React.FC<Props> = ({ stage }) => {
  const preview = stage.preview as ChunksPreviewDTO | null | undefined;
  const [selectedIndex, setSelectedIndex] = React.useState<number | null>(
    preview?.chunks?.[0]?.index ?? null,
  );

  if (!preview) {
    return (
      <div className="text-sm text-gray-500">
        Chunk-превью недоступно.
      </div>
    );
  }

  const selectedChunk: ChunkPreviewDTO | undefined = preview.chunks.find(
    (chunk) => chunk.index === selectedIndex,
  );

  const reconstructedText =
    preview.reconstructed_text ||
    preview.chunks.map((chunk) => chunk.text).join("\n\n");

  return (
    <div className="h-full flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900">{stage.title}</h3>
        <p className="text-xs text-gray-500">{stage.description}</p>
      </div>

      <div className="grid grid-cols-12 gap-4 min-h-[70vh]">
        <div className="col-span-3 border border-gray-100 rounded-lg overflow-hidden bg-white">
          <div className="px-3 py-2 border-b bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Чанки
          </div>
          <div className="max-h-[70vh] overflow-y-auto">
            {preview.chunks.length > 0 ? (
              preview.chunks.map((chunk) => (
                <button
                  key={chunk.index}
                  type="button"
                  onClick={() => setSelectedIndex(chunk.index)}
                  className={`w-full text-left px-3 py-2 border-b border-gray-50 hover:bg-gray-50 ${
                    selectedIndex === chunk.index ? "bg-blue-50" : "bg-white"
                  }`}
                >
                  <div className="text-sm font-medium text-gray-800">
                    Чанк #{chunk.index}
                  </div>
                  <div className="text-[11px] text-gray-400">
                    стр. {chunk.page_from ?? "?"}–{chunk.page_to ?? "?"}
                  </div>
                </button>
              ))
            ) : (
              <div className="p-3 text-sm text-gray-500">Чанки отсутствуют.</div>
            )}
          </div>
        </div>

        <div className="col-span-9 space-y-4">
          <div className="border border-gray-100 rounded-lg bg-white p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Документ, собранный из чанков
            </p>
            <pre className="max-h-[34vh] overflow-auto whitespace-pre-wrap break-words text-sm leading-6 text-gray-700 font-sans">
              {reconstructedText || "Нет reconstructed text."}
            </pre>
          </div>

          <div className="border border-gray-100 rounded-lg bg-white p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Выбранный чанк
            </p>

            {selectedChunk ? (
              <div className="space-y-2">
                <p className="text-xs text-gray-500">
                  Индекс: {selectedChunk.index}
                  {selectedChunk.clause_uid
                    ? ` · clause_uid: ${selectedChunk.clause_uid}`
                    : ""}
                  {(selectedChunk.page_from || selectedChunk.page_to) &&
                    ` · страницы: ${selectedChunk.page_from ?? "?"}–${selectedChunk.page_to ?? "?"}`}
                </p>
                <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-700 font-sans">
                  {selectedChunk.text || "—"}
                </pre>
              </div>
            ) : (
              <div className="text-sm text-gray-500">
                Выбери чанк слева.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChunksStageViewer;

