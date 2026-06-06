// src/components/documents/pipeline/ChunksStageViewer.tsx

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
  | { type: "plain"; key: string; text: string }
  | { type: "highlight"; key: string; text: string; chunk: ChunkPreviewDTO };

type LayerKind = "section" | "clause" | "subclause";

interface DisplayItem {
  chunk: ChunkPreviewDTO;
  layer: LayerKind;
  position: number;
  total: number;
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

function trimText(text: string, maxChars = 1200): string {
  const normalized = normalizeChunkText(text).trim();
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, maxChars).trim()}…`;
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

function getChunkUid(chunk: ChunkPreviewDTO): string {
  return (chunk.effective_uid || chunk.clause_uid || "").trim();
}

function getLayerKind(chunk: ChunkPreviewDTO): LayerKind | null {
  const kind = (chunk.chunk_kind || "").trim().toLowerCase();
  if (kind === "section" || kind === "clause" || kind === "subclause") {
    return kind;
  }
  return null;
}

function getTopLevelUid(uid: string): string {
  const value = (uid || "").trim();
  if (!value) return "";

  const colonIdx = value.indexOf(":");
  if (colonIdx === -1) {
    const first = value.split(".")[0] || value;
    return first;
  }

  const scope = value.slice(0, colonIdx + 1);
  const tail = value.slice(colonIdx + 1);
  const first = tail.split(".")[0] || tail;
  return `${scope}${first}`;
}

function sortByIndex(a: ChunkPreviewDTO, b: ChunkPreviewDTO): number {
  return a.index - b.index;
}

function buildLayerBuckets(chunks: ChunkPreviewDTO[]): Record<LayerKind, ChunkPreviewDTO[]> {
  const buckets: Record<LayerKind, ChunkPreviewDTO[]> = {
    section: [],
    clause: [],
    subclause: [],
  };

  for (const chunk of chunks) {
    const kind = getLayerKind(chunk);
    if (!kind) continue;
    buckets[kind].push(chunk);
  }

  buckets.section.sort(sortByIndex);
  buckets.clause.sort(sortByIndex);
  buckets.subclause.sort(sortByIndex);

  return buckets;
}

function buildDisplayItems(
  chunks: ChunkPreviewDTO[],
  layer: LayerKind,
): DisplayItem[] {
  return chunks.map((chunk, idx) => ({
    chunk,
    layer,
    position: idx + 1,
    total: chunks.length,
  }));
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

function getCanonicalLayerTitle(layer: LayerKind): string {
  if (layer === "clause") return "Clause";
  if (layer === "subclause") return "Subclause";
  return "Section";
}

function getCanonicalLayerTabTitle(layer: LayerKind): string {
  if (layer === "clause") return "Clause layer";
  if (layer === "subclause") return "Subclause layer";
  return "Section layer";
}

function getFriendlyLayerTitle(layer: LayerKind): string {
  if (layer === "subclause") return "Evidence";
  if (layer === "section") return "Context";
  return "Clause";
}

function getPrimaryItemTitle(
  item: DisplayItem,
  isCanonical: boolean,
): string {
  if (isCanonical) {
    return `${getCanonicalLayerTitle(item.layer)} ${item.position}/${item.total}`;
  }
  return `${getFriendlyLayerTitle(item.layer)} ${item.position}/${item.total}`;
}

function getSecondaryItemLine(
  item: DisplayItem,
  isCanonical: boolean,
): string {
  const chunk = item.chunk;
  const parts: string[] = [];
  const uid = getChunkUid(chunk);

  parts.push(isCanonical ? item.layer : getFriendlyLayerTitle(item.layer).toLowerCase());

  if (uid) parts.push(`uid: ${uid}`);

  const pages = pageLabel(chunk);
  if (pages !== "—") parts.push(`стр. ${pages}`);

  if (chunk.segment_type) {
    parts.push(
      `segment: ${chunk.segment_type}${
        chunk.is_primary_segment ? " (PRIMARY)" : ""
      }`,
    );
  }

  return parts.join(" · ");
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

function findRelatedSection(
  selectedChunk: ChunkPreviewDTO | undefined,
  sections: ChunkPreviewDTO[],
): ChunkPreviewDTO | undefined {
  if (!selectedChunk) return undefined;
  if (!sections.length) return undefined;

  const kind = getLayerKind(selectedChunk);
  if (kind === "section") return selectedChunk;

  const uid = getChunkUid(selectedChunk);
  const topLevelUid = getTopLevelUid(uid);

  if (topLevelUid) {
    const exact = sections.find((s) => getChunkUid(s) === topLevelUid);
    if (exact) return exact;

    const topMatch = sections.find(
      (s) => getTopLevelUid(getChunkUid(s)) === topLevelUid,
    );
    if (topMatch) return topMatch;
  }

  const page = selectedChunk.page_from;
  if (typeof page === "number") {
    const byPage = sections.find((s) => {
      const from = s.page_from ?? null;
      const to = s.page_to ?? s.page_from ?? null;
      return from != null && to != null && page >= from && page <= to;
    });
    if (byPage) return byPage;
  }

  return sections[0];
}

/* ================================================================
 * Shared UI
 * ================================================================ */

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

const InfoPanel: React.FC<{
  title: string;
  description?: string;
  children: React.ReactNode;
}> = ({ title, description, children }) => (
  <section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)]">
    <div className="flex h-full min-h-0 flex-col px-3 pt-3">
      <PanelHeader title={title} description={description} />
      <div className="min-h-0 flex-1 overflow-hidden pb-3">{children}</div>
    </div>
  </section>
);

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

function SmallNote({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "warning";
}) {
  const toneClass =
    tone === "warning"
      ? "border-[color:color-mix(in_oklab,var(--color-warning)_30%,transparent)] bg-[var(--color-warning-highlight)] text-[var(--color-warning)]"
      : "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]";

  return (
    <div
      className={cn(
        "rounded-xl border px-3 py-2 text-xs leading-5",
        toneClass,
      )}
    >
      {children}
    </div>
  );
}

function getListPanelMeta(isCanonical: boolean): {
  title: string;
  description: string;
} {
  if (isCanonical) {
    return {
      title: "Canonical CHUNKS layers",
      description:
        "Показываются три разных слоя materialized chunks. Нумерация локальная внутри выбранного слоя, а не общая по документу.",
    };
  }

  return {
    title: "Основа анализа рисков (RAG evidence)",
    description:
      "Слева показаны рабочие evidence-chunks, на которых строится проверка. Context section показывается отдельно в карточке выбранного chunk'а.",
  };
}

function getDetailPanelMeta(isCanonical: boolean): {
  title: string;
  description: string;
} {
  if (isCanonical) {
    return {
      title: "Canonical materialized chunk",
      description:
        "Показывается один chunk выбранного слоя. UID — якорь chunk'а, а не обещание идеальной границы ровно по одному пункту.",
    };
  }

  return {
    title: "RAG evidence chunk",
    description:
      "Показывается рабочий retrieval-visible fragment и связанный context section этого раздела.",
  };
}

function LayerTabs({
  activeLayer,
  onChange,
  counts,
}: {
  activeLayer: LayerKind;
  onChange: (next: LayerKind) => void;
  counts: Record<LayerKind, number>;
}) {
  const layers: LayerKind[] = ["clause", "subclause", "section"];

  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {layers.map((layer) => {
        const count = counts[layer];
        const active = activeLayer === layer;
        const disabled = count <= 0;

        return (
          <button
            key={layer}
            type="button"
            disabled={disabled}
            onClick={() => onChange(layer)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs transition-colors",
              active
                ? "border-[color:color-mix(in_oklab,var(--color-primary)_30%,transparent)] bg-[var(--color-primary-highlight)] text-[var(--color-primary)]"
                : "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              disabled && "cursor-not-allowed opacity-50",
            )}
          >
            {getCanonicalLayerTabTitle(layer)} · {count}
          </button>
        );
      })}
    </div>
  );
}

function ContextSectionCard({
  chunk,
  onOpenAtLocation,
  documentId,
}: {
  chunk: ChunkPreviewDTO;
  onOpenAtLocation?: OpenViewerAtFn;
  documentId: string;
}) {
  const uid = getChunkUid(chunk);
  const text = normalizeChunkText(chunk.text);

  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-faint)]">
            Связанный context section
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {uid || "section"}
          </p>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            section · стр. {pageLabel(chunk)}
          </p>
        </div>

        {onOpenAtLocation && (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() =>
              onOpenAtLocation(buildChunkViewerPayload(documentId, chunk))
            }
          >
            Открыть section
          </Button>
        )}
      </div>

      <div className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3">
        <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-[var(--text-secondary)]">
          {trimText(text, 1000) || "—"}
        </pre>
      </div>
    </div>
  );
}

/* ================================================================
 * Main component
 * ================================================================ */

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

  const isCanonical = stage.representation?.is_canonical ?? true;

  const preview = useMemo(
    () => (isChunksPreviewDTO(stage.preview) ? stage.preview : null),
    [stage.preview],
  );

  const isSourcePaneMode =
    highlightedChunkIndices.length > 0 || traceLabel != null;

  const allChunks = useMemo<ChunkPreviewDTO[]>(() => {
    if (!preview) return [];

    const items: ChunkPreviewDTO[] = [];
    for (const seg of preview.segments ?? []) {
      if (!seg || !Array.isArray(seg.chunks)) continue;
      for (const ch of seg.chunks) {
        if (ch) items.push(ch);
      }
    }
    return items;
  }, [preview]);

  const layerBuckets = useMemo(() => buildLayerBuckets(allChunks), [allChunks]);

  const canonicalCounts = useMemo(
    () => ({
      clause: layerBuckets.clause.length,
      subclause: layerBuckets.subclause.length,
      section: layerBuckets.section.length,
    }),
    [layerBuckets],
  );

  const canonicalDefaultLayer: LayerKind = useMemo(() => {
    if (layerBuckets.clause.length) return "clause";
    if (layerBuckets.subclause.length) return "subclause";
    return "section";
  }, [layerBuckets]);

  const [activeCanonicalLayer, setActiveCanonicalLayer] =
    useState<LayerKind>("clause");

  useEffect(() => {
    if (!isCanonical) return;
    setActiveCanonicalLayer((prev) => {
      if (canonicalCounts[prev] > 0) return prev;
      return canonicalDefaultLayer;
    });
  }, [isCanonical, canonicalCounts, canonicalDefaultLayer]);

  const displayedLayer: LayerKind = useMemo(() => {
    if (isCanonical) {
      return canonicalCounts[activeCanonicalLayer] > 0
        ? activeCanonicalLayer
        : canonicalDefaultLayer;
    }
    if (layerBuckets.subclause.length > 0) return "subclause";
    return "section";
  }, [
    isCanonical,
    activeCanonicalLayer,
    canonicalCounts,
    canonicalDefaultLayer,
    layerBuckets,
  ]);

  const displayedChunks = useMemo(() => {
    return layerBuckets[displayedLayer] ?? [];
  }, [layerBuckets, displayedLayer]);

  const displayedItems = useMemo(
    () => buildDisplayItems(displayedChunks, displayedLayer),
    [displayedChunks, displayedLayer],
  );

  const highlightedSet = useMemo(
    () => new Set<number>(highlightedChunkIndices),
    [highlightedChunkIndices],
  );

  const highlightedChunks = useMemo(
    () => allChunks.filter((chunk) => highlightedSet.has(chunk.index)),
    [allChunks, highlightedSet],
  );

  const hasLinkedChunks = highlightedChunks.length > 0;
  const hasChunks = allChunks.length > 0;

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [jsonMode, setJsonMode] = useState<"chunk" | "snapshot">("chunk");

  const listItemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const inlineHighlightRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const snapshotRef = useRef<HTMLDivElement | null>(null);

  const effectiveSelectedIndex = useMemo(() => {
    if (!isStageReady || !hasChunks) return null;

    if (isSourcePaneMode) {
      if (selectedIndex != null && highlightedSet.has(selectedIndex)) {
        return selectedIndex;
      }
      return highlightedChunks[0]?.index ?? null;
    }

    if (
      selectedIndex != null &&
      displayedChunks.some((chunk) => chunk.index === selectedIndex)
    ) {
      return selectedIndex;
    }

    return displayedChunks[0]?.index ?? null;
  }, [
    displayedChunks,
    hasChunks,
    highlightedChunks,
    highlightedSet,
    isSourcePaneMode,
    isStageReady,
    selectedIndex,
  ]);

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

  const selectedItem = useMemo(
    () =>
      effectiveSelectedIndex == null
        ? undefined
        : displayedItems.find((item) => item.chunk.index === effectiveSelectedIndex),
    [displayedItems, effectiveSelectedIndex],
  );

  const selectedChunk = selectedItem?.chunk;

  const relatedContextSection = useMemo(
    () =>
      !isCanonical
        ? findRelatedSection(selectedChunk, layerBuckets.section)
        : undefined,
    [isCanonical, selectedChunk, layerBuckets.section],
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

  /* ================================================================
   * Source pane mode
   * ================================================================ */

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
                          title={getChunkUid(segment.chunk) || `chunk ${segment.chunk.index}`}
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
          </div>
        </InfoPanel>
      </div>
    );
  }

  const listMeta = getListPanelMeta(isCanonical);
  const detailMeta = getDetailPanelMeta(isCanonical);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-3">
      {/* Левая панель */}
      <InfoPanel title={listMeta.title} description={listMeta.description}>
        <div className="flex h-full min-h-0 flex-col">
          <div className="mb-3 space-y-2">
            {isCanonical ? (
              <>
                <LayerTabs
                  activeLayer={displayedLayer}
                  onChange={setActiveCanonicalLayer}
                  counts={canonicalCounts}
                />
                <SmallNote>
                  Важный момент:{" "}
                  <span className="font-medium text-[var(--text-secondary)]">
                    нумерация локальная внутри выбранного слоя
                  </span>
                  . Например, Clause 1/81 — это первый clause-layer chunk, а не
                  “общий чанк #1 документа”. Технический index хранится в
                  JSON/debug.
                </SmallNote>
              </>
            ) : (
              <>
                <div className="flex flex-wrap gap-2">
                  <Pill tone="accent">
                    evidence: {layerBuckets.subclause.length}
                  </Pill>
                  <Pill>context: {layerBuckets.section.length}</Pill>
                </div>
                <SmallNote>
                  Слева показываются только{" "}
                  <span className="font-medium text-[var(--text-secondary)]">
                    evidence-chunks
                  </span>
                  , то есть рабочие retrieval fragments. Связанный section
                  показывается в карточке справа как context.
                </SmallNote>
              </>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-[var(--border-subtle)]">
            {displayedItems.length > 0 ? (
              <div className="divide-y divide-[var(--border-subtle)]">
                {displayedItems.map((item) => {
                  const isSelected = item.chunk.index === effectiveSelectedIndex;
                  const uid = getChunkUid(item.chunk);

                  return (
                    <button
                      key={item.chunk.index}
                      ref={(el) => {
                        if (el) {
                          listItemRefs.current.set(item.chunk.index, el);
                        } else {
                          listItemRefs.current.delete(item.chunk.index);
                        }
                      }}
                      type="button"
                      onClick={() => setSelectedIndex(item.chunk.index)}
                      className={cn(
                        "w-full px-3 py-2.5 text-left transition-colors",
                        isSelected
                          ? "bg-[var(--color-primary-highlight)]"
                          : "bg-[var(--bg-card)] hover:bg-[var(--bg-subtle)]",
                      )}
                      aria-pressed={isSelected}
                      title={uid || `chunk ${item.chunk.index}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-[var(--text-primary)]">
                            {getPrimaryItemTitle(item, isCanonical)}
                          </div>
                          <div className="mt-0.5 text-xs text-[var(--text-muted)]">
                            {getSecondaryItemLine(item, isCanonical)}
                          </div>
                        </div>

                        {uid ? (
                          <div className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-1 text-[10px] leading-none text-[var(--text-muted)]">
                            {uid}
                          </div>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="px-3 py-3 text-sm text-[var(--text-muted)]">
                Нет чанков в выбранном слое.
              </div>
            )}
          </div>
        </div>
      </InfoPanel>

      {/* Средняя панель */}
      <InfoPanel title={detailMeta.title} description={detailMeta.description}>
        <div className="flex h-full min-h-0 flex-col">
          <div className="min-h-0 flex-1 overflow-auto">
            {selectedChunk && selectedItem ? (
              <div className="space-y-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4">
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {getPrimaryItemTitle(selectedItem, isCanonical)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-faint)]">
                    {getSecondaryItemLine(selectedItem, isCanonical)}
                  </p>

                  <div className="mt-2 flex flex-wrap gap-2">
                    <Pill tone="accent">
                      layer: {selectedItem.layer}
                    </Pill>

                    {getChunkUid(selectedChunk) && (
                      <Pill>uid: {getChunkUid(selectedChunk)}</Pill>
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

                    <Pill>
                      tech index: {selectedChunk.index}
                    </Pill>

                    {selectedChunk.retrieval_safe === true && (
                      <Pill tone="accent">✓ retrieval-safe</Pill>
                    )}
                    {selectedChunk.retrieval_safe === false && (
                      <Pill tone="warning">⚠ not retrieval-safe</Pill>
                    )}
                  </div>
                </div>

                {isCanonical ? (
                  <>
                    <SmallNote>
                      <span className="font-medium text-[var(--text-secondary)]">
                        UID — это anchor identity chunk'а
                      </span>
                      , а не гарантия, что text будет идеально совпадать ровно с
                      одним видимым пунктом договора. Поэтому chunk с uid
                      `main_contract:2.1` может содержать текст 2.2, 2.3 и
                      следующие строки того же блока.
                    </SmallNote>

                    {selectedItem.layer === "clause" &&
                      normalizeChunkText(selectedChunk.text).length > 800 && (
                        <SmallNote tone="warning">
                          <span className="font-medium">
                            Leaf-node clause chunk:
                          </span>{" "}
                          этот clause layer chunk соответствует leaf-узлу
                          clause tree. Внутренние нумерованные подпункты могут не
                          быть отдельными clause-узлами.
                        </SmallNote>
                      )}

                    {(selectedItem.layer === "clause" ||
                      selectedItem.layer === "subclause") && (
                      <SmallNote>
                        Показывается raw materialized text. На границе chunk'а
                        может встречаться заголовок следующего раздела или
                        пограничная строка соседнего блока.
                      </SmallNote>
                    )}

                    {selectedItem.layer === "section" && (
                      <SmallNote>
                        Это context section layer: такой chunk может содержать
                        целый раздел договора и нужен как крупный контекстный
                        слой.
                      </SmallNote>
                    )}
                  </>
                ) : (
                  <>
                    <SmallNote>
                      Это working{" "}
                      <span className="font-medium text-[var(--text-secondary)]">
                        evidence chunk
                      </span>{" "}
                      retrieval corpus. Ниже отдельно показан связанный{" "}
                      <span className="font-medium">context section</span>,
                      чтобы пользователь видел не только фрагмент, но и более
                      широкий раздел документа.
                    </SmallNote>
                  </>
                )}

                <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-faint)]">
                    Текст chunk'а
                  </p>
                  <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
                    {normalizeChunkText(selectedChunk.text) || "—"}
                  </pre>
                </div>

                {!isCanonical && relatedContextSection && (
                  <ContextSectionCard
                    chunk={relatedContextSection}
                    onOpenAtLocation={onOpenAtLocation}
                    documentId={documentId}
                  />
                )}

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

      {/* Правая панель */}
      <InfoPanel
        title={jsonMode === "chunk" ? "JSON chunk'а" : "JSON snapshot"}
        description={
          jsonMode === "chunk"
            ? "Технический объект chunk'а. Здесь сохраняется raw index и backend metadata."
            : "Полный snapshot этапа; выделен фрагмент текста выбранного chunk'а."
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