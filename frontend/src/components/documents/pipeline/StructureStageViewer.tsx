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

interface SegmentSectionGroup {
  segmentId: string;
  label: string;
  segmentType: string | null;
  isPrimary: boolean;
  order: number | null;
  sections: StructureSectionPreviewDTO[];
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
    typeof section.page_from === "number"
      ? section.page_from
      : section.page_from ?? null;
  const to =
    typeof section.page_to === "number"
      ? section.page_to
      : section.page_to ?? null;

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
 * Canonical text секции:
 * - используется только structure_text;
 * - UI не использует дополнительные текстовые поля.
 */
function getSectionTextCanonical(
  section: StructureSectionPreviewDTO,
): {
  text: string;
  hasText: boolean;
} {
  const structure = (section.structure_text ?? "").trim();

  const text = structure;

  return {
    text,
    hasText: text.length > 0,
  };
}

function getSectionTextFriendly(section: StructureSectionPreviewDTO): string {
  const enriched = (section.enriched_text ?? "").trim();
  const structure = (section.structure_text ?? "").trim();

  return enriched || structure;
}

function getSectionLabel(section: StructureSectionPreviewDTO): string {
  return (section.title ?? "").trim() || "Без названия";
}

function getSectionMetaLine(section: StructureSectionPreviewDTO): string {
  const parts: string[] = [];

  parts.push(`Уровень ${section.level ?? 1}`);

  const pages = formatPageRange(section);
  if (pages) {
    parts.push(pages);
  }

  if (section.clause_uid) {
    parts.push(`clause_uid: ${section.clause_uid}`);
  }

  if (section.segment_type) {
    parts.push(
      `segment: ${section.segment_type}${
        section.is_primary_segment ? " (PRIMARY)" : ""
      }`,
    );
  }

  return parts.join(" · ");
}

/**
 * Короткое описание для навигационного списка слева.
 * Используется только v2-логика: enriched -> structure.
 */
function getSectionNavDescription(section: StructureSectionPreviewDTO): string {
  const enriched = (section.enriched_text ?? "").trim();
  const structure = (section.structure_text ?? "").trim();

  const text = enriched || structure;
  if (!text) return "";

  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

function groupSectionsBySegment(
  preview: StructurePreviewDTO,
): SegmentSectionGroup[] {
  if (!Array.isArray(preview.segments) || preview.segments.length === 0) {
    return [];
  }

  const result: SegmentSectionGroup[] = [];

  for (const seg of preview.segments) {
    if (
      !seg ||
      !seg.segment ||
      !Array.isArray(seg.sections) ||
      seg.sections.length === 0
    ) {
      continue;
    }

    const s = seg.segment;
    const segmentId = s.segment_id;
    const title = s.segment_title ?? "(без заголовка)";
    const type = s.segment_type ?? "primary";
    const order =
      typeof s.segment_order === "number" ? s.segment_order : null;
    const isPrimary = !!s.is_primary;

    const labelParts: string[] = [];
    if (order != null) labelParts.push(`#${order}`);
    labelParts.push(title);
    labelParts.push(type);
    if (isPrimary) labelParts.push("PRIMARY");

    result.push({
      segmentId,
      label: labelParts.join(" · "),
      segmentType: s.segment_type ?? null,
      isPrimary,
      order,
      sections: seg.sections,
    });
  }

  result.sort((a, b) => {
    if (a.isPrimary && !b.isPrimary) return -1;
    if (!a.isPrimary && b.isPrimary) return 1;
    const ao = a.order ?? 0;
    const bo = b.order ?? 0;
    return ao - bo;
  });

  return result;
}

export const StructureStageViewer: React.FC<Props> = ({
  structureStage,
  chunksStage,
}) => {
  const status = structureStage.status;
  const preview = structureStage.preview;

  // V2_ONLY: сначала честно обрабатываем status,
  // и только потом смотрим на наличие preview.
  if (status === "pending") {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Структура документа ещё не готова в v2-формате. Попробуй позже.
      </div>
    );
  }

  if (status === "missing") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Структурированный артефакт ожидается, но недоступен или повреждён.
        Проверь состояние пайплайна для стадии STRUCTURE.
      </div>
    );
  }

  if (!isStructurePreview(preview)) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Для этой стадии нет STRUCTURE-превью.
      </div>
    );
  }

  const isCanonical = isCanonicalStructureView(structureStage);

  const segmentGroups = React.useMemo(
    () => groupSectionsBySegment(preview),
    [preview],
  );

  const hasSegmentGroups = segmentGroups.length > 0;

  const sections: StructureSectionPreviewDTO[] = React.useMemo(() => {
    if (!hasSegmentGroups) {
      return [];
    }

    const all: StructureSectionPreviewDTO[] = [];
    for (const group of segmentGroups) {
      all.push(...group.sections);
    }
    return all;
  }, [hasSegmentGroups, segmentGroups]);

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
            <p className="mt-1 text-[11px] text-gray-400">
              Секций: {sectionCount}
            </p>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-1 py-2">
          {sections.length > 0 ? (
            hasSegmentGroups ? (
              <div className="space-y-2">
                {segmentGroups.map((group) => (
                  <div key={group.segmentId}>
                    <div className="flex items-center justify-between px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                      <span className="truncate">{group.label}</span>
                    </div>

                    <div className="space-y-1">
                      {group.sections.map((section) => (
                        <SectionNavItem
                          key={section.id}
                          section={section}
                          isActive={section.id === activeSectionId}
                          onSelect={() => setActiveSectionId(section.id)}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
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
            )
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
            sourceLabel="Здесь показывается текущий объект секции из preview.segments[].sections[]."
          />
        ) : chunksStage ? (
          chunksStage.status === "ready" ? (
            <ChunksStageViewer
              stage={chunksStage}
              highlightedChunkIndices={highlightedChunkIndices}
              traceLabel={
                highlightedChunkIndices.length > 0
                  ? "Фрагменты исходного текста, привязанные к выбранной секции"
                  : "Для выбранной секции не найдено связанных чанков"
              }
            />
          ) : chunksStage.status === "pending" ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-500">
              CHUNKS ещё не готовы в v2-формате. Попробуй позже.
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-red-700">
              CHUNKS-артефакт ожидается, но недоступен или повреждён.
            </div>
          )
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
      title={[
        section.clause_uid ? `clause_uid: ${section.clause_uid}` : null,
        pageRange,
        section.segment_type
          ? `segment: ${section.segment_type}${
              section.is_primary_segment ? " (PRIMARY)" : ""
            }`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate">{title}</div>
        {preview ? (
          <div className="mt-0.5 truncate text-[11px] text-gray-400">
            {preview}
          </div>
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

          <p className="mt-1 text-[11px] text-gray-400">
            {getSectionMetaLine(section)}
          </p>
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

          {section.segment_type ? (
            <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[11px] text-gray-700">
              {section.segment_type}
              {section.is_primary_segment ? " · PRIMARY" : ""}
            </span>
          ) : null}
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

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Segment ID
              </dt>
              <dd>{section.segment_id || "—"}</dd>
            </div>

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Segment Type
              </dt>
              <dd>{section.segment_type || "—"}</dd>
            </div>

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Segment Title
              </dt>
              <dd>{section.segment_title || "—"}</dd>
            </div>

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Segment Order
              </dt>
              <dd>
                {typeof section.segment_order === "number"
                  ? section.segment_order
                  : "—"}
              </dd>
            </div>

            <div>
              <dt className="text-[11px] uppercase tracking-wide text-gray-500">
                Primary Segment
              </dt>
              <dd>
                {typeof section.is_primary_segment === "boolean"
                  ? section.is_primary_segment
                    ? "true"
                    : "false"
                  : "—"}
              </dd>
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

          <p className="mt-1 text-[11px] text-gray-400">
            {getSectionMetaLine(section)}
          </p>
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

          {section.segment_type ? (
            <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[11px] text-gray-700">
              {section.segment_type}
              {section.is_primary_segment ? " · PRIMARY" : ""}
            </span>
          ) : null}
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
  sourceLabel: string;
}> = ({ sections, activeSectionId, sourceLabel }) => {
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
        <p className="mt-1 text-xs text-gray-400">{sourceLabel}</p>
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



