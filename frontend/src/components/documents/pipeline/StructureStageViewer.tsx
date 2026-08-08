// =============================================================
// src/components/documents/pipeline/StructureStageViewer.tsx
// =============================================================

import React from "react";
import type {
  PipelineStageViewDTO,
  StructurePreviewDTO,
  StructureSectionPreviewDTO,
  OpenViewerAtFn,
} from "../../../types";
import { ChunksStageViewer } from "./ChunksStageViewer";

interface Props {
  documentId: string;
  structureStage: PipelineStageViewDTO;
  chunksStage: PipelineStageViewDTO | null;
  onOpenAtLocation?: OpenViewerAtFn;
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
  return Boolean(
    preview && (preview as StructurePreviewDTO).type === "structure",
  );
}

function isCanonicalStructureView(stage: PipelineStageViewDTO): boolean {
  return stage.representation?.is_canonical ?? true;
}

function formatPageRange(
  section: StructureSectionPreviewDTO,
): string | null {
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

function buildSectionViewerPayload(
  documentId: string,
  section: StructureSectionPreviewDTO,
): Parameters<OpenViewerAtFn>[0] {
  return {
    documentId,
    page: section.page_from ?? undefined,
    clauseUid: section.clause_uid ?? undefined,
    elementId: undefined,
    segmentId: section.segment_id ?? undefined,
    chunkId: undefined,
    chunkIndex: undefined,
  };
}

function getSectionJson(section: StructureSectionPreviewDTO): string {
  try {
    return JSON.stringify(section, null, 2);
  } catch {
    return JSON.stringify({ id: section.id }, null, 2);
  }
}

function getSectionTextCanonical(section: StructureSectionPreviewDTO): {
  text: string;
  hasText: boolean;
} {
  const structure = (section.structure_text ?? "").trim();
  return { text: structure, hasText: structure.length > 0 };
}

function getSectionTextFriendly(
  section: StructureSectionPreviewDTO,
): string {
  const enriched = (section.enriched_text ?? "").trim();
  const structure = (section.structure_text ?? "").trim();
  return enriched || structure;
}

function getSectionLabel(section: StructureSectionPreviewDTO): string {
  return (section.title ?? "").trim() || "Без названия";
}

function getSectionMetaLine(
  section: StructureSectionPreviewDTO,
): string {
  const parts: string[] = [];

  parts.push(`Уровень ${section.level ?? 1}`);

  const pages = formatPageRange(section);
  if (pages) parts.push(pages);

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

function getSectionNavDescription(
  section: StructureSectionPreviewDTO,
): string {
  const enriched = (section.enriched_text ?? "").trim();
  const structure = (section.structure_text ?? "").trim();
  const text = enriched || structure;
  if (!text) return "";
  return text.length > 160 ? `${text.slice(0, 160)}…` : text;
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
    return (a.order ?? 0) - (b.order ?? 0);
  });

  return result;
}

/* ===== shared ui ===== */

const PanelHeader: React.FC<{
  title: string;
  description?: string;
}> = ({ title, description }) => (
  <div className="mb-3 h-[72px] border-b border-[var(--border-subtle)] pb-2">
    <div className="flex h-full flex-col items-start justify-start">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </p>
      {description ? (
        <p className="mt-1 text-xs leading-4 text-[var(--text-faint)]">
          {description}
        </p>
      ) : null}
    </div>
  </div>
);

/* ===== Status badges — канонический паттерн ===== */

const ChunksMappingBadge: React.FC<{ mapped: boolean }> = ({ mapped }) =>
  mapped ? (
    <span className="inline-flex items-center rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-2 py-0.5 text-xs text-[var(--color-success-text)]">
      Есть привязка к CHUNKS
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-2 py-0.5 text-xs text-[var(--color-warning-text)]">
      Нет привязки к CHUNKS для этой секции
    </span>
  );

/* ================================================================
 * Main component
 * ================================================================ */

export const StructureStageViewer: React.FC<Props> = ({
  documentId,
  structureStage,
  chunksStage,
  onOpenAtLocation,
}) => {
  const status = structureStage.status;
  const preview = structureStage.preview;

  const isPending = status === "pending";
  const isMissing = status === "missing";
  const structurePreview = isStructurePreview(preview) ? preview : null;

  const segmentGroups = React.useMemo(
    () =>
      structurePreview ? groupSectionsBySegment(structurePreview) : [],
    [structurePreview],
  );

  const hasSegmentGroups = segmentGroups.length > 0;

  const sections = React.useMemo<StructureSectionPreviewDTO[]>(() => {
    if (!hasSegmentGroups) return [];
    const all: StructureSectionPreviewDTO[] = [];
    for (const group of segmentGroups) {
      all.push(...group.sections);
    }
    return all;
  }, [hasSegmentGroups, segmentGroups]);

  const [activeSectionId, setActiveSectionId] = React.useState<
    string | null
  >(sections[0]?.id ?? null);

  React.useEffect(() => {
    setActiveSectionId((prev) => {
      if (prev && sections.some((s) => s.id === prev)) return prev;
      return sections[0]?.id ?? null;
    });
  }, [sections]);

  if (isPending) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)]">
        Структура документа ещё не готова в v2-формате. Попробуй позже.
      </div>
    );
  }

  if (isMissing) {
    return (
      <div className="rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] p-4 text-sm text-[var(--color-error-text)]">
        Структурированный артефакт ожидается, но недоступен или повреждён.
        Проверь состояние пайплайна для стадии STRUCTURE.
      </div>
    );
  }

  if (!structurePreview) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)]">
        Для этой стадии нет STRUCTURE-превью.
      </div>
    );
  }

  const isCanonical = isCanonicalStructureView(structureStage);
  const sectionCount =
    structureStage.meta?.section_count ?? sections.length;

  const highlightedChunkIndices =
    activeSectionId != null
      ? (() => {
          const active = sections.find((s) => s.id === activeSectionId);
          return active?.source_mapping?.source_stage === "CHUNKS"
            ? active.source_mapping.chunk_indices ?? []
            : [];
        })()
      : [];

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-3">
      {/* ── Левая панель: навигация по секциям ── */}
      <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">
        <PanelHeader
          title="Структура документа"
          description={
            sectionCount > 0 ? `Секций: ${sectionCount}` : undefined
          }
        />

        <div className="min-h-0 flex-1 overflow-auto px-1">
          {sections.length > 0 ? (
            hasSegmentGroups ? (
              <div className="space-y-2.5">
                {segmentGroups.map((group) => (
                  <div key={group.segmentId}>
                    <div className="flex items-center justify-between px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-[var(--text-faint)]">
                      <span className="truncate">{group.label}</span>
                    </div>

                    <div className="space-y-1">
                      {group.sections.map((section) => (
                        <SectionNavItem
                          key={section.id}
                          section={section}
                          isActive={section.id === activeSectionId}
                          onSelect={() =>
                            setActiveSectionId(section.id)
                          }
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
            <div className="px-3 py-2 text-sm text-[var(--text-muted)]">
              В STRUCTURE пока нет секций.
            </div>
          )}
        </div>
      </aside>

      {/* ── Средняя панель: детали секции ── */}
      <section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">
        {isCanonical ? (
          <CanonicalSectionPanel
            sections={sections}
            activeSectionId={activeSectionId}
            documentId={documentId}
            onOpenAtLocation={onOpenAtLocation}
          />
        ) : (
          <FriendlySectionPanel
            sections={sections}
            activeSectionId={activeSectionId}
            documentId={documentId}
            onOpenAtLocation={onOpenAtLocation}
          />
        )}
      </section>

      {/* ── Правая панель: JSON или chunks ── */}
      <section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">
        {isCanonical ? (
          <CanonicalJsonPanel
            sections={sections}
            activeSectionId={activeSectionId}
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
              documentId={documentId}
              onOpenAtLocation={onOpenAtLocation}
            />
          ) : chunksStage.status === "pending" ? (
            <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
              CHUNKS ещё не готовы в v2-формате. Попробуй позже.
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-[var(--color-error-text)]">
              CHUNKS-артефакт ожидается, но недоступен или повреждён.
            </div>
          )
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
            CHUNKS-стадия недоступна — показать исходный текст невозможно.
          </div>
        )}
      </section>
    </div>
  );
};

/* ===== Sub-components ===================================================== */

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
        "flex w-full items-start gap-2 rounded-xl py-1.5 text-left transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
        isActive
          ? "bg-[var(--bg-elevated-soft)] text-[var(--text-primary)] ring-1 ring-[color:color-mix(in_oklab,var(--accent-primary)_35%,transparent)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]",
      )}
      style={{ paddingLeft: `${8 + indent * 12}px`, paddingRight: "8px" }}
      title={[
        section.clause_uid
          ? `clause_uid: ${section.clause_uid}`
          : null,
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
        <div className="truncate text-xs font-medium">{title}</div>
        {preview ? (
          <div className="mt-0.5 line-clamp-2 text-xs leading-4 text-[var(--text-faint)]">
            {preview}
          </div>
        ) : null}
      </div>

      {hasSourceChunks ? (
        <span
          className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-success)]"
          aria-label="Есть привязка к CHUNKS"
        />
      ) : hasClauseUid ? (
        <span
          className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]"
          aria-label="Есть clause_uid"
        />
      ) : null}
    </button>
  );
};

const CanonicalSectionPanel: React.FC<{
  sections: StructureSectionPreviewDTO[];
  activeSectionId: string | null;
  documentId: string;
  onOpenAtLocation?: OpenViewerAtFn;
}> = ({ sections, activeSectionId, documentId, onOpenAtLocation }) => {
  if (!sections.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
        В STRUCTURE пока нет секций.
      </div>
    );
  }

  const section =
    activeSectionId != null
      ? (sections.find((s) => s.id === activeSectionId) ?? sections[0])
      : sections[0];

  if (!section) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
        Выбери секцию слева.
      </div>
    );
  }

  const pageRange = formatPageRange(section);
  const sourceMapped = hasChunksMapping(section);
  const { text: previewText, hasText } = getSectionTextCanonical(section);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PanelHeader
        title="Сведения о секции"
        description="В canonical‑режиме здесь показывается узел структуры документа (structure_text), а не enriched‑текст из CHUNKS."
      />

      <div className="min-h-0 flex-1 space-y-3 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3">
        <div>
          <p
            className="text-sm font-semibold text-[var(--text-primary)]"
            title={
              section.clause_uid
                ? `clause_uid: ${section.clause_uid}`
                : undefined
            }
          >
            {getSectionLabel(section)}
          </p>
          <p className="mt-1 text-xs leading-4 text-[var(--text-faint)]">
            {getSectionMetaLine(section)}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <ChunksMappingBadge mapped={sourceMapped} />

          {section.segment_type ? (
            <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
              {section.segment_type}
              {section.is_primary_segment ? " · PRIMARY" : ""}
            </span>
          ) : null}
        </div>

        <div className="rounded-xl bg-[var(--bg-card)] px-3 py-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-faint)]">
            Поля узла
          </p>

          <dl className="space-y-2 text-xs text-[var(--text-secondary)]">
            {[
              { label: "ID", value: section.id || "—", breakAll: true },
              {
                label: "Clause UID",
                value: section.clause_uid || "—",
              },
              {
                label: "Уровень",
                value: String(section.level ?? 1),
              },
              { label: "Страницы", value: pageRange ?? "—" },
              {
                label: "Segment ID",
                value: section.segment_id || "—",
              },
              {
                label: "Segment Type",
                value: section.segment_type || "—",
              },
              {
                label: "Segment Title",
                value: section.segment_title || "—",
              },
              {
                label: "Segment Order",
                value:
                  typeof section.segment_order === "number"
                    ? String(section.segment_order)
                    : "—",
              },
              {
                label: "Primary Segment",
                value:
                  typeof section.is_primary_segment === "boolean"
                    ? section.is_primary_segment
                      ? "true"
                      : "false"
                    : "—",
              },
            ].map(({ label, value, breakAll }) => (
              <div key={label}>
                <dt className="text-xs uppercase tracking-wide text-[var(--text-faint)]">
                  {label}
                </dt>
                <dd className={breakAll ? "break-all" : undefined}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        {hasText ? (
          <div className="rounded-xl bg-[var(--bg-card)] px-3 py-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-faint)]">
              Текст clause tree (structure_text)
            </p>
            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
              {previewText}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-3">
            <p className="text-sm leading-6 text-[var(--text-muted)]">
              Для этого узла текст clause tree не задан. Это нормально для
              canonical STRUCTURE, если в дереве есть только заголовок и
              метаданные узла.
            </p>
          </div>
        )}

        {onOpenAtLocation && (
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={() =>
                onOpenAtLocation(
                  buildSectionViewerPayload(documentId, section),
                )
              }
              className="inline-flex items-center rounded-full border border-[color:color-mix(in_oklab,var(--accent-primary)_40%,transparent)] bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
            >
              Открыть в документе
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

const FriendlySectionPanel: React.FC<{
  sections: StructureSectionPreviewDTO[];
  activeSectionId: string | null;
  documentId: string;
  onOpenAtLocation?: OpenViewerAtFn;
}> = ({ sections, activeSectionId, documentId, onOpenAtLocation }) => {
  if (!sections.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
        В STRUCTURE пока нет секций.
      </div>
    );
  }

  const section =
    activeSectionId != null
      ? (sections.find((s) => s.id === activeSectionId) ?? sections[0])
      : sections[0];

  if (!section) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
        Выбери секцию слева.
      </div>
    );
  }

  const sourceMapped = hasChunksMapping(section);
  const previewText = getSectionTextFriendly(section);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PanelHeader
        title="Текст секции"
        description="В friendly‑режиме здесь показывается текст секции, обогащённый из CHUNKS (enriched_text), с fallback на structure_text."
      />

      <div className="min-h-0 flex-1 space-y-3 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3">
        <div>
          <p
            className="text-sm font-semibold text-[var(--text-primary)]"
            title={
              section.clause_uid
                ? `clause_uid: ${section.clause_uid}`
                : undefined
            }
          >
            {getSectionLabel(section)}
          </p>
          <p className="mt-1 text-xs leading-4 text-[var(--text-faint)]">
            {getSectionMetaLine(section)}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <ChunksMappingBadge mapped={sourceMapped} />

          {section.segment_type ? (
            <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
              {section.segment_type}
              {section.is_primary_segment ? " · PRIMARY" : ""}
            </span>
          ) : null}
        </div>

        {previewText ? (
          <div className="rounded-xl bg-[var(--bg-card)] px-3 py-3">
            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
              {previewText}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-3">
            <p className="text-sm leading-6 text-[var(--text-muted)]">
              Для этой секции нет текстового превью.
            </p>
          </div>
        )}

        {onOpenAtLocation && (
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={() =>
                onOpenAtLocation(
                  buildSectionViewerPayload(documentId, section),
                )
              }
              className="inline-flex items-center rounded-full border border-[color:color-mix(in_oklab,var(--accent-primary)_40%,transparent)] bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
            >
              Открыть в документе
            </button>
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
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
        В STRUCTURE пока нет секций.
      </div>
    );
  }

  const section =
    activeSectionId != null
      ? (sections.find((s) => s.id === activeSectionId) ?? sections[0])
      : sections[0];

  if (!section) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
        Выбери секцию слева.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PanelHeader
        title="JSON узла"
        description="Здесь показывается текущий объект секции из preview.segments[].sections[]."
      />

      <div className="min-h-0 flex-1 overflow-auto rounded-2xl bg-[var(--bg-inverse)] p-3">
        <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-[var(--text-inverse)]">
          {getSectionJson(section)}
        </pre>
      </div>
    </div>
  );
};

export default StructureStageViewer;


