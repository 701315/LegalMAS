// =============================================================
// src/components/documents/pipeline/ChunksStageViewer.tsx
// =============================================================

import React, {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { twMerge } from "tailwind-merge";
import type {
  ChunkPreviewDTO,
  ChunksPreviewDTO,
  PipelineStageViewDTO,
  OpenViewerAtFn,
} from "../../../types";
import Button from "../../ui/Button";

interface Props {
  stage: PipelineStageViewDTO;
  highlightedChunkIndices?: number[];
  traceLabel?: string | null;
  documentId: string;
  onOpenAtLocation?: OpenViewerAtFn;
}

type RenderSegment =
  | {
      type: "plain";
      key: string;
      text: string;
    }
  | {
      type: "highlight";
      key: string;
      text: string;
      chunk: ChunkPreviewDTO;
    };

type ChunkGroupKey = "sections" | "clauses" | "subclauses";

interface ChunkGroup {
  key: ChunkGroupKey;
  label: string;
  description: string;
  items: ChunkPreviewDTO[];
}

interface SegmentGroup {
  segmentId: string;
  label: string;
  description: string;
  segmentType: string | null;
  isPrimary: boolean;
  order: number | null;
  items: ChunkPreviewDTO[];
}

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

function isChunksPreviewDTO(value: unknown): value is ChunksPreviewDTO {
  return Boolean(
    value &&
      typeof value === "object" &&
      "chunks" in (value as Record<string, unknown>) &&
      Array.isArray((value as Record<string, unknown>).chunks),
  );
}

function normalizeChunkText(text: unknown): string {
  return typeof text === "string" ? text : "";
}

function pageLabel(chunk: ChunkPreviewDTO): string {
  const from = typeof chunk.page_from === "number" ? chunk.page_from : null;
  const to =
    typeof chunk.page_to === "number"
      ? chunk.page_to
      : typeof chunk.page_from === "number"
        ? chunk.page_from
        : null;

  if (from == null && to == null) return "—";
  if (from != null && to != null) {
    return from === to ? `${from}` : `${from}–${to}`;
  }
  return String(from ?? to ?? "—");
}

function chunkTitle(chunk: ChunkPreviewDTO): string {
  return `Чанк #${chunk.index}`;
}

function chunkMetaLine(chunk: ChunkPreviewDTO): string {
  const parts: string[] = [];
  const pages = pageLabel(chunk);

  if (pages !== "—") {
    parts.push(`стр. ${pages}`);
  }

  if (chunk.clause_uid) {
    parts.push(`clause_uid: ${chunk.clause_uid}`);
  }

  if (chunk.segment_type) {
    parts.push(
      `segment: ${chunk.segment_type}${
        chunk.is_primary_segment ? " (PRIMARY)" : ""
      }`,
    );
  }

  return parts.length ? parts.join(" · ") : "Без метаданных";
}

function buildChunkViewerPayload(
  documentId: string,
  chunk: ChunkPreviewDTO,
): Parameters<OpenViewerAtFn>[0] {
  return {
    documentId,
    page: chunk.page_from ?? undefined,
    clauseUid: chunk.clause_uid ?? undefined,
    elementId: undefined,
    segmentId: chunk.segment_id ?? undefined,
    chunkId: chunk.chunk_id ?? undefined,
    chunkIndex: typeof chunk.index === "number" ? chunk.index : undefined,
  };
}

function fallbackReconstructedText(chunks: ChunkPreviewDTO[]): string {
  return chunks
    .map((chunk) => normalizeChunkText(chunk.text).trim())
    .filter(Boolean)
    .join("\n\n");
}

function stageRawJson(preview: ChunksPreviewDTO): string {
  const raw = preview.raw_json ?? { chunks: preview.chunks };
  try {
    return JSON.stringify(raw, null, 2);
  } catch {
    return JSON.stringify({ chunks: preview.chunks }, null, 2);
  }
}

function chunkJson(chunk: ChunkPreviewDTO): string {
  try {
    return JSON.stringify(chunk, null, 2);
  } catch {
    return JSON.stringify({ index: chunk.index }, null, 2);
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function buildHighlightedSnapshot(
  preview: ChunksPreviewDTO,
  selectedChunk: ChunkPreviewDTO | undefined,
): { __html: string } {
  const raw = stageRawJson(preview);
  const chunkTextFull = selectedChunk
    ? normalizeChunkText(selectedChunk.text).trim()
    : "";

  if (!chunkTextFull) {
    return { __html: escapeHtml(raw) };
  }

  const normalized = chunkTextFull.replace(/\s+/g, " ").trim();
  const snippet = normalized.slice(0, 80);
  if (!snippet) {
    return { __html: escapeHtml(raw) };
  }

  let idx = raw.indexOf(snippet);
  if (idx === -1 && snippet.length > 30) {
    const shorter = snippet.slice(0, 30);
    idx = raw.indexOf(shorter);
    if (idx === -1) {
      return { __html: escapeHtml(raw) };
    }
  } else if (idx === -1) {
    return { __html: escapeHtml(raw) };
  }

  const before = escapeHtml(raw.slice(0, idx));
  const middle = escapeHtml(raw.slice(idx, idx + snippet.length));
  const after = escapeHtml(raw.slice(idx + snippet.length));

  return {
    __html: `${before}<mark data-snapshot-chunk="true">${middle}</mark>${after}`,
  };
}

/* ===== grouping: sections / clauses / subclauses ===== */

function getClauseDepthFromString(value: string | null | undefined): number {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return 0;
  return trimmed.split(".").filter(Boolean).length;
}

function getChunkClauseDepth(chunk: ChunkPreviewDTO): number {
  return getClauseDepthFromString(chunk.clause_uid);
}

function getChunkGroupKey(chunk: ChunkPreviewDTO): ChunkGroupKey {
  const depth = getChunkClauseDepth(chunk);
  if (depth === 0) return "sections";
  if (depth <= 2) return "clauses";
  return "subclauses";
}

function groupChunks(chunks: ChunkPreviewDTO[]): ChunkGroup[] {
  const sections: ChunkPreviewDTO[] = [];
  const clauses: ChunkPreviewDTO[] = [];
  const subclauses: ChunkPreviewDTO[] = [];

  for (const chunk of chunks) {
    const key = getChunkGroupKey(chunk);
    if (key === "sections") sections.push(chunk);
    else if (key === "clauses") clauses.push(chunk);
    else subclauses.push(chunk);
  }

  sections.sort((a, b) => a.index - b.index);
  clauses.sort((a, b) => a.index - b.index);
  subclauses.sort((a, b) => a.index - b.index);

  return [
    {
      key: "sections",
      label: "Sections",
      description: "Крупные section‑подобные чанки без clause_uid.",
      items: sections,
    },
    {
      key: "clauses",
      label: "Clauses",
      description: "Материализованные clauses с глубиной clause_uid 1–2.",
      items: clauses,
    },
    {
      key: "subclauses",
      label: "Subclauses",
      description: "Более глубокие подпункты с глубиной clause_uid 3+.",
      items: subclauses,
    },
  ];
}

/* ===== grouping by segments v2 ===== */

function groupChunksBySegment(
  preview: ChunksPreviewDTO | null,
): SegmentGroup[] {
  if (
    !preview ||
    !Array.isArray(preview.segments) ||
    preview.segments.length === 0
  ) {
    return [];
  }

  const result: SegmentGroup[] = [];

  for (const seg of preview.segments) {
    if (
      !seg ||
      !seg.segment ||
      !Array.isArray(seg.chunks) ||
      seg.chunks.length === 0
    ) {
      continue;
    }

    const s = seg.segment;
    const segmentId = s.segment_id;
    const title = s.segment_title || "(без заголовка)";
    const type = s.segment_type || "primary";
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
      description: `Сегмент ${segmentId}`,
      segmentType: s.segment_type ?? null,
      isPrimary,
      order,
      items: seg.chunks.filter(Boolean),
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
}> = ({ title, description }) => {
  return (
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
};

const InfoPanel: React.FC<{
  title: string;
  description?: string;
  children: React.ReactNode;
}> = ({ title, description, children }) => {
  return (
    <section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)]">
      <div className="flex h-full min-h-0 flex-col px-3 pt-3">
        <PanelHeader title={title} description={description} />
        <div className="min-h-0 flex-1 overflow-hidden pb-3">{children}</div>
      </div>
    </section>
  );
};

function Pill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "accent" | "warning";
}) {
  const toneClass =
    tone === "accent"
      ? "border-[color:color-mix(in_oklab,var(--color-primary)_25%,transparent)] bg-[var(--color-primary-highlight)] text-[var(--color-primary)]"
      : tone === "warning"
        ? "border-[color:color-mix(in_oklab,var(--color-warning)_30%,transparent)] bg-[var(--color-warning-highlight)] text-[var(--color-warning)]"
        : "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-1 text-xs leading-none",
        toneClass,
      )}
    >
      {children}
    </span>
  );
}

export const ChunksStageViewer: React.FC<Props> = ({
  stage,
  highlightedChunkIndices = [],
  traceLabel = null,
  documentId,
  onOpenAtLocation,
}) => {
  const status = stage.status;
  const isPending = status === "pending";
  const isMissing = status === "missing";
  const isStageReady = !isPending && !isMissing;

  const preview = useMemo(
    () => (isChunksPreviewDTO(stage.preview) ? stage.preview : null),
    [stage.preview],
  );

  const isSourcePaneMode =
    highlightedChunkIndices.length > 0 || traceLabel != null;

  const allChunks = useMemo<ChunkPreviewDTO[]>(() => {
    if (!preview) return [];

    if (Array.isArray(preview.segments) && preview.segments.length > 0) {
      const fromSegments: ChunkPreviewDTO[] = [];
      for (const seg of preview.segments) {
        if (!seg || !Array.isArray(seg.chunks)) continue;
        for (const ch of seg.chunks) {
          if (ch) fromSegments.push(ch);
        }
      }
      return fromSegments;
    }

    return [];
  }, [preview]);

  const hasChunks = allChunks.length > 0;

  const chunkGroups = useMemo(() => groupChunks(allChunks), [allChunks]);
  const segmentGroups = useMemo(
    () => groupChunksBySegment(preview),
    [preview],
  );
  const hasSegmentGroups = segmentGroups.length > 0;

  const highlightedSet = useMemo(
    () => new Set<number>(highlightedChunkIndices),
    [highlightedChunkIndices],
  );

  const highlightedChunks = useMemo(
    () => allChunks.filter((chunk) => highlightedSet.has(chunk.index)),
    [allChunks, highlightedSet],
  );

  const hasLinkedChunks = highlightedChunks.length > 0;

  // User intent: какой индекс выбрал пользователь кликом.
  // Не синхронизируется эффектом — только явный onClick.
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [jsonMode, setJsonMode] = useState<"chunk" | "snapshot">("chunk");

  const listItemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const inlineHighlightRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const snapshotRef = useRef<HTMLDivElement | null>(null);

  const [expandedGroups, setExpandedGroups] = useState<
    Record<ChunkGroupKey, boolean>
  >({
    sections: false,
    clauses: true,
    subclauses: false,
  });

  const [expandedSegments, setExpandedSegments] = useState<
    Record<string, boolean>
  >({});

  const toggleGroup = (key: ChunkGroupKey) => {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleSegment = (segmentId: string) => {
    setExpandedSegments((prev) => ({
      ...prev,
      [segmentId]: !prev[segmentId],
    }));
  };

  // Derived: актуальный выбранный индекс с учётом текущих данных.
  // selectedIndex — user intent, который может устареть при смене данных.
  // effectiveSelectedIndex — то, что реально используется в рендере и scroll.
  const effectiveSelectedIndex = useMemo(() => {
    if (!isStageReady || !hasChunks) {
      return null;
    }

    if (isSourcePaneMode) {
      if (selectedIndex != null && highlightedSet.has(selectedIndex)) {
        return selectedIndex;
      }
      return highlightedChunks[0]?.index ?? null;
    }

    if (
      selectedIndex != null &&
      allChunks.some((chunk) => chunk.index === selectedIndex)
    ) {
      return selectedIndex;
    }

    return allChunks[0]?.index ?? null;
  }, [
    allChunks,
    hasChunks,
    highlightedChunks,
    highlightedSet,
    isSourcePaneMode,
    isStageReady,
    selectedIndex,
  ]);

  // Scroll к активному элементу при смене effectiveSelectedIndex.
  useEffect(() => {
    if (effectiveSelectedIndex == null) return;

    const listButton = listItemRefs.current.get(effectiveSelectedIndex);
    if (listButton) {
      listButton.scrollIntoView({ block: "nearest", behavior: "smooth" });
      return;
    }

    const inlineButton =
      inlineHighlightRefs.current.get(effectiveSelectedIndex);
    if (inlineButton) {
      inlineButton.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [effectiveSelectedIndex]);

  const selectedChunk = useMemo(
    () =>
      effectiveSelectedIndex == null
        ? undefined
        : allChunks.find((c) => c.index === effectiveSelectedIndex),
    [allChunks, effectiveSelectedIndex],
  );

  const reconstructedText = useMemo(() => {
    const raw = preview?.reconstructed_text;
    if (typeof raw === "string" && raw.trim()) return raw;
    return fallbackReconstructedText(allChunks);
  }, [preview, allChunks]);

  const renderSegments = useMemo<RenderSegment[]>(() => {
    if (!hasChunks) return [];
    return allChunks.map((chunk) => {
      const text = normalizeChunkText(chunk.text);
      if (highlightedSet.has(chunk.index)) {
        return {
          type: "highlight",
          key: `highlight-${chunk.index}`,
          text,
          chunk,
        };
      }
      return {
        type: "plain",
        key: `plain-${chunk.index}`,
        text,
      };
    });
  }, [allChunks, hasChunks, highlightedSet]);

  const highlightedSnapshot = useMemo(
    () =>
      preview
        ? buildHighlightedSnapshot(preview, selectedChunk)
        : { __html: "" },
    [preview, selectedChunk],
  );

  useLayoutEffect(() => {
    if (!snapshotRef.current || jsonMode !== "snapshot") return;
    const mark = snapshotRef.current.querySelector<HTMLElement>(
      "mark[data-snapshot-chunk='true']",
    );
    if (mark) {
      mark.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [jsonMode, highlightedSnapshot.__html, selectedChunk?.index]);

  if (isPending) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)]">
        Чанки ещё не готовы в v2-формате. Попробуй позже.
      </div>
    );
  }

  if (isMissing) {
    return (
      <div className="rounded-2xl border border-[color:color-mix(in_oklab,var(--color-error)_40%,transparent)] bg-[var(--color-error-highlight)] p-4 text-sm text-[var(--color-error)]">
        CHUNKS-артефакт ожидается, но недоступен или повреждён. Проверь
        состояние пайплайна для стадии CHUNKS.
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)]">
        CHUNKS preview недоступен для этого этапа.
      </div>
    );
  }

  if (isSourcePaneMode) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        {traceLabel && (
          <div className="rounded-2xl border border-[color:color-mix(in_oklab,var(--color-primary)_30%,transparent)] bg-[var(--color-primary-highlight)] px-3 py-2 text-xs text-[var(--color-primary)]">
            {traceLabel}
          </div>
        )}

        <InfoPanel
          title="Исходный текст документа"
          description={
            hasLinkedChunks
              ? "Связанные с выбранной секцией чанки подсвечены inline."
              : "Для выбранной секции не найдено связанных chunk'ов."
          }
        >
          <div className="flex h-full min-h-0 flex-col">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div />
              {hasLinkedChunks && (
                <Pill tone="warning">
                  Подсвечено: {highlightedChunks.length}
                </Pill>
              )}
            </div>

            <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-4">
              {hasChunks ? (
                <div className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
                  {renderSegments.map((segment) => {
                    if (segment.type === "highlight") {
                      const isSelected =
                        effectiveSelectedIndex === segment.chunk.index;
                      const titleParts = [
                        chunkTitle(segment.chunk),
                        `стр. ${pageLabel(segment.chunk)}`,
                        segment.chunk.clause_uid
                          ? `clause_uid: ${segment.chunk.clause_uid}`
                          : null,
                      ].filter(Boolean);

                      return (
                        <button
                          key={segment.key}
                          ref={(el) => {
                            if (el) {
                              inlineHighlightRefs.current.set(
                                segment.chunk.index,
                                el,
                              );
                            } else {
                              inlineHighlightRefs.current.delete(
                                segment.chunk.index,
                              );
                            }
                          }}
                          type="button"
                          onClick={() => setSelectedIndex(segment.chunk.index)}
                          className={cn(
                            "inline whitespace-pre-wrap break-words rounded-md px-1 py-0.5 text-left transition-colors",
                            isSelected
                              ? "bg-[var(--color-warning)]/20 ring-1 ring-[var(--color-warning)] text-[var(--text-primary)]"
                              : "bg-[var(--color-warning-highlight)] hover:bg-[var(--color-warning-highlight)]/80",
                          )}
                          title={titleParts.join(" · ")}
                        >
                          {segment.text || " "}
                        </button>
                      );
                    }

                    return (
                      <React.Fragment key={segment.key}>
                        {segment.text}
                      </React.Fragment>
                    );
                  })}
                </div>
              ) : (
                <div className="text-sm text-[var(--text-muted)]">
                  Исходный текст документа недоступен.
                </div>
              )}
            </div>

            <div className="mt-3 min-h-[1.5rem]">
              {selectedChunk ? (
                <p className="text-xs text-[var(--text-muted)]">
                  Активная подсветка: {chunkTitle(selectedChunk)}
                  {pageLabel(selectedChunk) !== "—" &&
                    ` · страницы: ${pageLabel(selectedChunk)}`}
                  {selectedChunk.clause_uid &&
                    ` · clause_uid: ${selectedChunk.clause_uid}`}
                </p>
              ) : (
                <p className="text-xs text-[var(--text-muted)]">
                  Нет активного chunk'а для подсветки.
                </p>
              )}
            </div>
          </div>
        </InfoPanel>
      </div>
    );
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-3">
      <InfoPanel
        title="CHUNKS: materialized chunks"
        description="Материализованные чанки этапа, сгруппированные по сегментам или уровню."
      >
        <div className="min-h-0 flex h-full flex-col">
          <div className="min-h-0 flex-1 overflow-auto rounded-xl">
            {hasChunks ? (
              <div className="divide-y divide-[var(--border-subtle)]">
                {hasSegmentGroups
                  ? segmentGroups.map((group) => {
                      const isExpanded =
                        expandedSegments[group.segmentId] ?? true;
                      const count = group.items.length;
                      if (count === 0) return null;

                      return (
                        <div key={group.segmentId}>
                          <button
                            type="button"
                            onClick={() => toggleSegment(group.segmentId)}
                            className="flex w-full items-center justify-between gap-2 rounded-xl bg-[var(--bg-elevated-soft)] px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-faint)] transition-colors hover:bg-[var(--bg-subtle)]"
                          >
                            <span className="flex min-w-0 items-center gap-2">
                              <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border border-[var(--border)] bg-[var(--bg-card)] text-[10px] leading-none text-[var(--text-muted)]">
                                {isExpanded ? "−" : "+"}
                              </span>
                              <span className="truncate">{group.label}</span>
                            </span>
                            <span className="text-xs font-normal text-[var(--text-muted)]">
                              {count}
                            </span>
                          </button>

                          {isExpanded && (
                            <div className="mt-1 border-t border-[var(--border-subtle)]">
                              {group.items.map((chunk) => {
                                const isSelected =
                                  effectiveSelectedIndex === chunk.index;
                                return (
                                  <button
                                    key={chunk.index}
                                    ref={(el) => {
                                      if (el) {
                                        listItemRefs.current.set(
                                          chunk.index,
                                          el,
                                        );
                                      } else {
                                        listItemRefs.current.delete(
                                          chunk.index,
                                        );
                                      }
                                    }}
                                    type="button"
                                    onClick={() =>
                                      setSelectedIndex(chunk.index)
                                    }
                                    className={cn(
                                      "w-full px-3 py-2.5 text-left transition-colors",
                                      isSelected
                                        ? "bg-[var(--color-primary-highlight)]"
                                        : "bg-[var(--bg-card)] hover:bg-[var(--bg-subtle)]",
                                    )}
                                    aria-pressed={isSelected}
                                    title={chunkMetaLine(chunk)}
                                  >
                                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                                      {chunkTitle(chunk)}
                                    </div>
                                    <div className="mt-0.5 text-xs text-[var(--text-muted)]">
                                      {chunkMetaLine(chunk)}
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })
                  : chunkGroups.map((group) => {
                      const isExpanded = expandedGroups[group.key];
                      const count = group.items.length;
                      if (count === 0) return null;

                      return (
                        <div key={group.key}>
                          <button
                            type="button"
                            onClick={() => toggleGroup(group.key)}
                            className="flex w-full items-center justify-between gap-2 rounded-xl bg-[var(--bg-elevated-soft)] px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-faint)] transition-colors hover:bg-[var(--bg-subtle)]"
                          >
                            <span className="flex min-w-0 items-center gap-2">
                              <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border border-[var(--border)] bg-[var(--bg-card)] text-[10px] leading-none text-[var(--text-muted)]">
                                {isExpanded ? "−" : "+"}
                              </span>
                              <span className="truncate">{group.label}</span>
                            </span>
                            <span className="text-xs font-normal text-[var(--text-muted)]">
                              {count}
                            </span>
                          </button>

                          {isExpanded && (
                            <div className="mt-1 border-t border-[var(--border-subtle)]">
                              {group.items.map((chunk) => {
                                const isSelected =
                                  effectiveSelectedIndex === chunk.index;

                                return (
                                  <button
                                    key={chunk.index}
                                    ref={(el) => {
                                      if (el) {
                                        listItemRefs.current.set(
                                          chunk.index,
                                          el,
                                        );
                                      } else {
                                        listItemRefs.current.delete(
                                          chunk.index,
                                        );
                                      }
                                    }}
                                    type="button"
                                    onClick={() =>
                                      setSelectedIndex(chunk.index)
                                    }
                                    className={cn(
                                      "w-full px-3 py-2.5 text-left transition-colors",
                                      isSelected
                                        ? "bg-[var(--color-primary-highlight)]"
                                        : "bg-[var(--bg-card)] hover:bg-[var(--bg-subtle)]",
                                    )}
                                    aria-pressed={isSelected}
                                    title={chunkMetaLine(chunk)}
                                  >
                                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                                      {chunkTitle(chunk)}
                                    </div>
                                    <div className="mt-0.5 text-xs text-[var(--text-muted)]">
                                      {chunkMetaLine(chunk)}
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
              </div>
            ) : (
              <div className="px-1 py-2 text-sm text-[var(--text-muted)]">
                В v2-артефакте CHUNKS нет сегментов или чанков.
              </div>
            )}
          </div>
        </div>
      </InfoPanel>

      <InfoPanel
        title="Выбранный chunk"
        description="Canonical‑представление materialized chunks."
      >
        <div className="flex h-full min-h-0 flex-col">
          <div className="min-h-0 flex-1 overflow-auto">
            {selectedChunk ? (
              <div className="space-y-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4">
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {chunkTitle(selectedChunk)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-faint)]">
                    {chunkMetaLine(selectedChunk)}
                  </p>

                  <div className="mt-2 flex flex-wrap gap-2">
                    <Pill>index: {selectedChunk.index}</Pill>

                    {selectedChunk.clause_uid && (
                      <Pill>clause_uid: {selectedChunk.clause_uid}</Pill>
                    )}

                    {pageLabel(selectedChunk) !== "—" && (
                      <Pill>pages: {pageLabel(selectedChunk)}</Pill>
                    )}

                    {selectedChunk.segment_type && (
                      <Pill>
                        segment: {selectedChunk.segment_type}
                        {selectedChunk.is_primary_segment ? " (PRIMARY)" : ""}
                      </Pill>
                    )}

                    <Pill>
                      chars: {normalizeChunkText(selectedChunk.text).length}
                    </Pill>
                  </div>
                </div>

                <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-faint)]">
                    Текст chunk'а
                  </p>
                  <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
                    {normalizeChunkText(selectedChunk.text) || "—"}
                  </pre>
                </div>

                {reconstructedText ? (
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-faint)]">
                      Контекст stage
                    </p>
                    <p className="text-xs leading-5 text-[var(--text-muted)]">
                      Справа можно переключаться между JSON выбранного chunk'а и
                      полным snapshot этапа, прокручиваемым к этому chunk'у.
                    </p>
                  </div>
                ) : null}

                {onOpenAtLocation && (
                  <div className="mt-2 flex justify-end">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        onOpenAtLocation(
                          buildChunkViewerPayload(documentId, selectedChunk),
                        )
                      }
                    >
                      Открыть в документе
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
                Выбери chunk слева.
              </div>
            )}
          </div>
        </div>
      </InfoPanel>

      <InfoPanel
        title={jsonMode === "chunk" ? "JSON chunk'а" : "JSON snapshot"}
        description={
          jsonMode === "chunk"
            ? "Текущий объект materialized chunk'а из snapshot CHUNKS."
            : "Полный canonical snapshot CHUNKS; выделен фрагмент текста выбранного chunk'а."
        }
      >
        <div className="flex h-full min-h-0 flex-col">
          <div className="mb-3 flex items-center justify-end">
            <div className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-1">
              <button
                type="button"
                onClick={() => setJsonMode("chunk")}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs leading-none transition-colors",
                  jsonMode === "chunk"
                    ? "bg-[var(--text-primary)] text-[var(--bg-card)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)]",
                )}
              >
                chunk
              </button>
              <button
                type="button"
                onClick={() => setJsonMode("snapshot")}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs leading-none transition-colors",
                  jsonMode === "snapshot"
                    ? "bg-[var(--text-primary)] text-[var(--bg-card)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)]",
                )}
              >
                snapshot
              </button>
            </div>
          </div>

          {jsonMode === "chunk" ? (
            selectedChunk ? (
              <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[#050816] p-3">
                <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-[#f9fafb]">
                  {chunkJson(selectedChunk)}
                </pre>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
                Выбери chunk слева.
              </div>
            )
          ) : (
            <div
              ref={snapshotRef}
              className="min-h-0 flex-1 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[#050816] p-3"
            >
              <pre
                className="whitespace-pre-wrap break-words text-xs leading-5 text-[#f9fafb] [&_mark[data-snapshot-chunk='true']]:rounded [&_mark[data-snapshot-chunk='true']]:bg-[var(--color-warning)]/25 [&_mark[data-snapshot-chunk='true']]:px-1"
                dangerouslySetInnerHTML={highlightedSnapshot}
              />
            </div>
          )}
        </div>
      </InfoPanel>
    </div>
  );
};

export default ChunksStageViewer;



