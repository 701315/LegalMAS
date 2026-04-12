import React from "react";
import type {
  PipelineStageViewDTO,
  StructurePreviewDTO,
  StructureSectionPreviewDTO,
} from "../../../types";
import { ChunksStageViewer } from "./ChunksStageViewer";

interface Props {
  structureStage: PipelineStageViewDTO;
  chunksStage: PipelineStageViewDTO | null;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function isStructurePreview(
  preview: PipelineStageViewDTO["preview"],
): preview is StructurePreviewDTO {
  return Boolean(preview && (preview as StructurePreviewDTO).type === "structure");
}

function isCanonicalStructureView(stage: PipelineStageViewDTO): boolean {
  return stage.representation?.is_canonical ?? true;
}

function formatPageRange(section: StructureSectionPreviewDTO): string | null {
  const from =
    typeof section.page_from === "number" ? section.page_from : section.page_from ?? null;
  const to =
    typeof section.page_to === "number" ? section.page_to : section.page_to ?? null;

  if (from == null && to == null) return null;
  if (from != null && to != null) {
    return from === to ? `стр. ${from}` : `стр. ${from}–${to}`;
  }
  return `стр. ${from ?? to ?? "?"}`;
}

function hasChunksMapping(section: StructureSectionPreviewDTO): boolean {
  return (
    section.source_mapping?.source_stage === "CHUNKS" &&
    (section.source_mapping?.chunk_indices?.length ?? 0) > 0
  );
}

function getSectionJson(section: StructureSectionPreviewDTO): string {
  try {
    return JSON.stringify(section, null, 2);
  } catch {
    return JSON.stringify({ id: section.id }, null, 2);
  }
}

/**
 * Универсальный helper для выбора текста секции
 * с корректным fallback:
 *
 * canonical:
 *   - сначала structure_text;
 *   - затем text_preview (для старых бэкендов);
 *
 * friendly:
 *   - сначала enriched_text;
 *   - затем structure_text;
 *   - затем text_preview (на случай старых бэкендов).
 */
function getSectionTextCanonical(section: StructureSectionPreviewDTO): {
  text: string;
  hasText: boolean;
} {
  const structure = (section.structure_text ?? "").trim();
  const preview = (section.text_preview ?? "").trim();

  const text = structure || preview;

  return {
    text,
    hasText: text.length > 0,
  };
}

function getSectionTextFriendly(section: StructureSectionPreviewDTO): string {
  const enriched = (section.enriched_text ?? "").trim();
  const structure = (section.structure_text ?? "").trim();
  const preview = (section.text_preview ?? "").trim();

  return enriched || structure || preview;
}

function getSectionLabel(section: StructureSectionPreviewDTO): string {
  return (section.title ?? "").trim() || "Без названия";
}

function getSectionMetaLine(section: StructureSectionPreviewDTO): string {
  return [
    `Уровень ${section.level ?? 1}`,
    formatPageRange(section),
    section.clause_uid ? `clause_uid: ${section.clause_uid}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * Короткое описание для навигационного списка слева.
 * Здесь достаточно укороченного текста секции
 * с общим fallback: enriched -> structure -> text_preview.
 */
function getSectionNavDescription(section: StructureSectionPreviewDTO): string {
  const enriched = (section.enriched_text ?? "").trim();
  const structure = (section.structure_text ?? "").trim();
  const preview = (section.text_preview ?? "").trim();

  const text = enriched || structure || preview;
  if (!text) return "";

  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

export const StructureStageViewer: React.FC<Props> = ({
  structureStage,
  chunksStage,
}) => {
  const preview = structureStage.preview;

  if (!isStructurePreview(preview)) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Для этой стадии нет STRUCTURE-превью.
      </div>
    );
  }

  const isCanonical = isCanonicalStructureView(structureStage);
  const sections = preview.sections ?? [];
  const sectionCount = structureStage.meta?.section_count ?? sections.length;

  const [activeSectionId, setActiveSectionId] = React.useState<string | null>(
    sections[0]?.id ?? null,
  );

  React.useEffect(() => {
    setActiveSectionId((prev) => {
      if (prev && sections.some((s) => s.id === prev)) {
        return prev;
      }
      return sections[0]?.id ?? null;
    });
  }, [sections]);

  const activeSection: StructureSectionPreviewDTO | null = React.useMemo(() => {
    if (!sections.length) return null;
    if (!activeSectionId) return sections[0];
    return sections.find((s) => s.id === activeSectionId) ?? sections[0];
  }, [sections, activeSectionId]);

  const highlightedChunkIndices =
    activeSection && activeSection.source_mapping?.source_stage === "CHUNKS"
      ? activeSection.source_mapping.chunk_indices ?? []
      : [];

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-[25%_30%_45%]">
      <aside className="flex min-h-0 flex-col rounded-lg border border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
            Структура документа
          </p>
          {sectionCount > 0 && (
            <p className="mt-1 text-[11px] text-gray-400">Секций: {sectionCount}</p>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-1 py-2">
          {sections.length > 0 ? (
            <div className="space-y-1">
              {sections.map((section) => (
                <SectionNavItem
                  key={section.id}
                  section={section}
                  isActive={section.id === activeSectionId}
                  onSelect={() => setActiveSectionId(section.id)}
                />
              ))}
            </div>
          ) : (
            <div className="px-3 py-2 text-sm text-gray-500">
              В STRUCTURE пока нет секций.
            </div>
          )}
        </div>
      </aside>

      <section className="min-h-0 min-w-0 overflow-hidden rounded-lg border border-gray-200 bg-white p-3">
        {isCanonical ? (
          <CanonicalSectionPanel
            sections={sections}
            activeSectionId={activeSectionId}
          />
        ) : (
          <FriendlySectionPanel
            sections={sections}
            activeSectionId={activeSectionId}
          />
        )}
      </section>

      <section className="min-h-0 min-w-0 overflow-hidden rounded-lg border border-gray-200 bg-white p-3">
        {isCanonical ? (
          <CanonicalJsonPanel
            sections={sections}
            activeSectionId={activeSectionId}
          />
        ) : chunksStage ? (
          <ChunksStageViewer
            stage={chunksStage}
            highlightedChunkIndices={highlightedChunkIndices}
            traceLabel={
              highlightedChunkIndices.length > 0
                ? "Фрагменты исходного текста, привязанные к выбранной секции"
                : "Для выбранной секции не найдено связанных чанков"
            }
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-gray-500">
            CHUNKS-стадия недоступна — показать исходный текст невозможно.
          </div>
        )}
      </section>
    </div>
  );
};

const SectionNavItem: React.FC<{
  section: StructureSectionPreviewDTO;
  isActive: boolean;
  onSelect: () => void;
}> = ({ section, isActive, onSelect }) => {
  const indent = Math.max(0, (section.level ?? 1) - 1);
  const hasClauseUid = Boolean(section.clause_uid);
  const hasSourceChunks = hasChunksMapping(section);
  const pageRange = formatPageRange(section);
  const title = getSectionLabel(section);
  const preview = getSectionNavDescription(section);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cx(
        "flex w-full items-start gap-2 rounded-md py-1.5 text-left text-xs transition-colors",
        isActive ? "bg-blue-50 text-blue-800" : "text-gray-700 hover:bg-gray-50",
      )}
      style={{ paddingLeft: `${8 + indent * 12}px`, paddingRight: "8px" }}
      title={[section.clause_uid ? `clause_uid: ${section.clause_uid}` : null, pageRange]
        .filter(Boolean)
        .join(" · ")}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate">{title}</div>
        {preview ? (
          <div className="mt-0.5 truncate text-[11px] text-gray-400">{preview}</div>
        ) : null}
      </div>

      {hasSourceChunks ? (
        <span
          className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"
          aria-label="Есть привязка к CHUNKS"
        />
      ) : hasClauseUid ? (
        <span
          className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400"
          aria-label="Есть clause_uid"
        />
      ) : null}
    </button>
  );
};

const CanonicalSectionPanel: React.FC<{
  sections: StructureSectionPreviewDTO[];
  activeSectionId: string | null;
}> = ({ sections, activeSectionId }) => {
  if (!sections.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-500">
        В STRUCTURE пока нет секций.
      </div>
    );
  }

  const section =
    activeSectionId != null
      ? sections.find((s) => s.id === activeSectionId) ?? sections[0]
      : sections[0];

  if (!section) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-500">
        Выбери секцию слева.
      </div>
    );
  }

  const pageRange = formatPageRange(section);
  const sourceMapped = hasChunksMapping(section);
  const { text: previewText, hasText } = getSectionTextCanonical(section);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-3 border-b border-gray-100 pb-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
          Сведения о секции
        </p>
        <p className="mt-1 text-xs text-gray-400">
          В canonical‑режиме здесь показывается узел структуры документа
          (structure_text), а не enriched‑текст из CHUNKS.
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-auto rounded-lg border border-gray-200 bg-white p-4">
        <div>
          <p
            className="text-sm font-semibold text-gray-900"
            title={section.clause_uid ? `clause_uid: ${section.clause_uid}` : undefined}
          >
            {getSectionLabel(section)}
          </p>

          <p className="mt-1 text-[11px] text-gray-400">{getSectionMetaLine(section)}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          {sourceMapped ? (
            <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">
              Есть привязка к CHUNKS
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700">
              Нет привязки к CHUNKS для этой секции
            </span>
          )}
        </div>

        <div className="rounded-md bg-gray-50 px-3 py-3">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-500">
            Поля узла
          </p>

          <dl className="space-y-2 text-sm text-gray-700">
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">ID</dt>
              <dd className="break-all">{section.id || "—"}</dd>
            </div>

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Clause UID
              </dt>
              <dd>{section.clause_uid || "—"}</dd>
            </div>

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Уровень
              </dt>
              <dd>{section.level ?? 1}</dd>
            </div>

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Страницы
              </dt>
              <dd>{pageRange ?? "—"}</dd>
            </div>
          </dl>
        </div>

        {hasText ? (
          <div className="rounded-md bg-gray-50 px-3 py-3">
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-500">
              Текст clause tree (structure_text)
            </p>
            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-700">
              {previewText}
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 px-3 py-3">
            <p className="text-sm text-gray-500">
              Для этого узла текст clause tree не задан. Это нормально для canonical
              STRUCTURE, если в дереве есть только заголовок и метаданные узла.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

const FriendlySectionPanel: React.FC<{
  sections: StructureSectionPreviewDTO[];
  activeSectionId: string | null;
}> = ({ sections, activeSectionId }) => {
  if (!sections.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-500">
        В STRUCTURE пока нет секций.
      </div>
    );
  }

  const section =
    activeSectionId != null
      ? sections.find((s) => s.id === activeSectionId) ?? sections[0]
      : sections[0];

  if (!section) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-500">
        Выбери секцию слева.
      </div>
    );
  }

  const sourceMapped = hasChunksMapping(section);
  const previewText = getSectionTextFriendly(section);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-3 border-b border-gray-100 pb-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
          Текст секции
        </p>
        <p className="mt-1 text-xs text-gray-400">
          В friendly‑режиме здесь показывается текст секции, обогащённый из CHUNKS
          (enriched_text), с fallback на structure_text.
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-auto rounded-lg border border-gray-200 bg-white p-4">
        <div>
          <p
            className="text-sm font-semibold text-gray-900"
            title={section.clause_uid ? `clause_uid: ${section.clause_uid}` : undefined}
          >
            {getSectionLabel(section)}
          </p>

          <p className="mt-1 text-[11px] text-gray-400">{getSectionMetaLine(section)}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          {sourceMapped ? (
            <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">
              Есть привязка к CHUNKS
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700">
              Нет привязки к CHUNKS для этой секции
            </span>
          )}
        </div>

        {previewText ? (
          <div className="rounded-md bg-gray-50 px-3 py-3">
            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-700">
              {previewText}
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 px-3 py-3">
            <p className="text-sm text-gray-500">
              Для этой секции нет текстового превью.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

const CanonicalJsonPanel: React.FC<{
  sections: StructureSectionPreviewDTO[];
  activeSectionId: string | null;
}> = ({ sections, activeSectionId }) => {
  if (!sections.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-500">
        В STRUCTURE пока нет секций.
      </div>
    );
  }

  const section =
    activeSectionId != null
      ? sections.find((s) => s.id === activeSectionId) ?? sections[0]
      : sections[0];

  if (!section) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-500">
        Выбери секцию слева.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-3 border-b border-gray-100 pb-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
          JSON узла
        </p>
        <p className="mt-1 text-xs text-gray-400">
          Здесь показывается текущий объект секции из <code>preview.sections[]</code>.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto rounded-md bg-gray-950 p-3">
        <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-gray-100">
          {getSectionJson(section)}
        </pre>
      </div>
    </div>
  );
};

export default StructureStageViewer;


