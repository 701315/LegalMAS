import React, {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  ChunkPreviewDTO,
  ChunksPreviewDTO,
  PipelineStageViewDTO,
} from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
  highlightedChunkIndices?: number[];
  traceLabel?: string | null;
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

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
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

/**
 * Подсветка фрагмента текста chunk’а внутри snapshot JSON.
 * Ищем первые N символов текста chunk’а как сырую подстроку.
 */
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

  // Нормализуем пробелы, чтобы чуть повысить шанс совпадения
  const normalized = chunkTextFull.replace(/\s+/g, " ").trim();
  const snippet = normalized.slice(0, 80);
  if (!snippet) {
    return { __html: escapeHtml(raw) };
  }

  let idx = raw.indexOf(snippet);
  if (idx === -1 && snippet.length > 30) {
    // Fallback: попробуем более короткий кусок
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

/* ===== ГРУППИРОВКА CHUNKS: sections / clauses / subclauses ===== */

function getClauseDepthFromString(value: string | null | undefined): number {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return 0;
  return trimmed.split(".").filter(Boolean).length;
}

function getChunkClauseDepth(chunk: ChunkPreviewDTO): number {
  // Основной источник — clause_uid, но если его нет, глубина 0 (section‑подобный чанк).
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
    if (key === "sections") {
      sections.push(chunk);
    } else if (key === "clauses") {
      clauses.push(chunk);
    } else {
      subclauses.push(chunk);
    }
  }

  // Можно слегка отсортировать внутри групп по index
  sections.sort((a, b) => a.index - b.index);
  clauses.sort((a, b) => a.index - b.index);
  subclauses.sort((a, b) => a.index - b.index);

  const result: ChunkGroup[] = [];

  result.push({
    key: "sections",
    label: "Sections",
    description: "Крупные section‑подобные чанки (без clause_uid).",
    items: sections,
  });

  result.push({
    key: "clauses",
    label: "Clauses",
    description:
      "Обычные materialized clauses (clause_uid глубиной 1–2, напр. 2, 2.3, 4.7).",
    items: clauses,
  });

  result.push({
    key: "subclauses",
    label: "Subclauses",
    description:
      "Более глубокие подпункты (clause_uid глубиной 3+ — 2.2.10, 3.1.1, 6.1.5).",
    items: subclauses,
  });

  return result;
}

/* ===== ГРУППИРОВКА CHUNKS ПО СЕГМЕНТАМ (v2) ===== */

function groupChunksBySegment(preview: ChunksPreviewDTO | null): SegmentGroup[] {
  if (!preview || !Array.isArray(preview.segments) || preview.segments.length === 0) {
    return [];
  }

  const result: SegmentGroup[] = [];

  for (const seg of preview.segments) {
    if (!seg || !seg.segment || !Array.isArray(seg.chunks) || seg.chunks.length === 0) {
      continue;
    }

    const s = seg.segment;
    const segmentId = s.segment_id;
    const title = s.segment_title || "(без заголовка)";
    const type = s.segment_type || "primary";
    const order = typeof s.segment_order === "number" ? s.segment_order : null;
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

  // Сортируем сегменты: primary выше, затем по order
  result.sort((a, b) => {
    if (a.isPrimary && !b.isPrimary) return -1;
    if (!a.isPrimary && b.isPrimary) return 1;
    const ao = a.order ?? 0;
    const bo = b.order ?? 0;
    return ao - bo;
  });

  return result;
}

export const ChunksStageViewer: React.FC<Props> = ({
  stage,
  highlightedChunkIndices = [],
  traceLabel = null,
}) => {
  const status = stage.status;

  // V2_ONLY: сначала честно обрабатываем status.
  if (status === "pending") {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Чанки ещё не готовы в v2-формате. Попробуй позже.
      </div>
    );
  }

  if (status === "missing") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        CHUNKS-артефакт ожидается, но недоступен или повреждён.
        Проверь состояние пайплайна для стадии CHUNKS.
      </div>
    );
  }

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

    // V2_ONLY: если сегментов нет, считаем, что canonical corpus отсутствует.
    return [];
  }, [preview]);








  const hasChunks = allChunks.length > 0;

  const chunkGroups = useMemo<ChunkGroup[]>(
    () => groupChunks(allChunks),
    [allChunks],
  );

  const segmentGroups = useMemo<SegmentGroup[]>(
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

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [jsonMode, setJsonMode] = useState<"chunk" | "snapshot">("chunk");

  const listItemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const inlineHighlightRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const snapshotRef = useRef<HTMLDivElement | null>(null);

  // Состояние развёрнутости групп в левой колонке (legacy depth-группы)
  const [expandedGroups, setExpandedGroups] = useState<
    Record<ChunkGroupKey, boolean>
  >({
    sections: false,
    clauses: true,
    subclauses: false,
  });

  const toggleGroup = (key: ChunkGroupKey) => {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Состояние развёрнутости сегментов (v2)
  const [expandedSegments, setExpandedSegments] = useState<Record<string, boolean>>(
    {},
  );

  const toggleSegment = (segmentId: string) => {
    setExpandedSegments((prev) => ({
      ...prev,
      [segmentId]: !prev[segmentId],
    }));
  };

  // Инициализация выбранного чанка
  useEffect(() => {
    if (!hasChunks) {
      setSelectedIndex(null);
      return;
    }

    if (isSourcePaneMode) {
      setSelectedIndex((prev) => {
        if (prev != null && highlightedSet.has(prev)) return prev;
        return highlightedChunks[0]?.index ?? null;
      });
      return;
    }

    setSelectedIndex((prev) => {
      if (prev != null && allChunks.some((chunk) => chunk.index === prev)) {
        return prev;
      }
      return allChunks[0]?.index ?? null;
    });
  }, [allChunks, hasChunks, highlightedChunks, highlightedSet, isSourcePaneMode]);

  // Скролл к элементу в списке/inline подсветке
  useEffect(() => {
    if (selectedIndex == null) return;

    const listButton = listItemRefs.current.get(selectedIndex);
    if (listButton) {
      listButton.scrollIntoView({ block: "nearest", behavior: "smooth" });
      return;
    }

    const inlineButton = inlineHighlightRefs.current.get(selectedIndex);
    if (inlineButton) {
      inlineButton.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selectedIndex]);

  const selectedChunk = useMemo(
    () =>
      selectedIndex == null
        ? undefined
        : allChunks.find((c) => c.index === selectedIndex),
    [allChunks, selectedIndex],
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
      preview ? buildHighlightedSnapshot(preview, selectedChunk) : { __html: "" },
    [preview, selectedChunk],
  );

  // Скролл к mark после обновления DOM с новым snapshot’ом
  useLayoutEffect(() => {
    if (!snapshotRef.current || jsonMode !== "snapshot") return;
    const mark = snapshotRef.current.querySelector<HTMLElement>(
      "mark[data-snapshot-chunk='true']",
    );
    if (mark) {
      mark.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [jsonMode, highlightedSnapshot.__html, selectedChunk?.index]);

  if (!preview) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        CHUNKS preview недоступен для этого этапа.
      </div>
    );
  }

  /* SOURCE-PANE MODE */
  if (isSourcePaneMode) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        {traceLabel && (
          <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-[11px] text-blue-700">
            {traceLabel}
          </div>
        )}

        <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                Исходный текст документа
              </p>
              <p className="mt-1 text-xs text-gray-400">
                {hasLinkedChunks
                  ? "Связанные с выбранной секцией чанки подсвечены inline."
                  : "Для выбранной секции не найдено связанных chunk’ов."}
              </p>
            </div>

            {hasLinkedChunks && (
              <div className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">
                Подсвечено: {highlightedChunks.length}
              </div>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-gray-100 bg-gray-50 px-4 py-4">
            {hasChunks ? (
              <div className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-gray-700">
                {renderSegments.map((segment) => {
                  if (segment.type === "highlight") {
                    const isSelected = selectedIndex === segment.chunk.index;
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
                        className={cx(
                          "inline whitespace-pre-wrap break-words rounded px-1 py-0.5 text-left transition-colors",
                          isSelected
                            ? "bg-amber-300/80 ring-1 ring-amber-500"
                            : "bg-amber-100 hover:bg-amber-200",
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
              <div className="text-sm text-gray-500">
                Исходный текст документа недоступен.
              </div>
            )}
          </div>

          <div className="mt-3 min-h-[1.5rem]">
            {selectedChunk ? (
              <p className="text-xs text-gray-500">
                Активная подсветка: {chunkTitle(selectedChunk)}
                {pageLabel(selectedChunk) !== "—" &&
                  ` · страницы: ${pageLabel(selectedChunk)}`}
                {selectedChunk.clause_uid &&
                  ` · clause_uid: ${selectedChunk.clause_uid}`}
              </p>
            ) : (
              <p className="text-xs text-gray-400">
                Нет активного chunk’а для подсветки.
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  /* CANONICAL CHUNKS VIEW */
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-[25%_30%_45%]">
      {/* Левая колонка: список чанков, приоритет — сегменты v2 */}
      <aside className="flex min-h-0 flex-col rounded-lg border border-gray-200 bg-white">
        <div className="border-b bg-gray-50 px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
            CHUNKS
          </p>
          <p className="mt-1 text-[11px] text-gray-400">
            Материализованные чанки этапа, сгруппированные по сегментам или
            уровню.
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {hasChunks ? (
            <div className="divide-y divide-gray-100">
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
                          className="flex w-full items-center justify-between gap-2 bg-gray-50 px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500"
                        >
                          <span className="flex items-center gap-2">
                            <span
                              className={cx(
                                "inline-flex h-4 w-4 items-center justify-center rounded border border-gray-300 bg-white text-[9px] leading-none text-gray-600",
                              )}
                            >
                              {isExpanded ? "−" : "+"}
                            </span>
                            {group.label}
                          </span>
                          <span className="text-[10px] font-normal text-gray-400">
                            {count}
                          </span>
                        </button>

                        {isExpanded && (
                          <div className="border-t border-gray-100">
                            {group.items.map((chunk) => {
                              const isSelected = selectedIndex === chunk.index;
                              return (
                                <button
                                  key={chunk.index}
                                  ref={(el) => {
                                    if (el) {
                                      listItemRefs.current.set(chunk.index, el);
                                    } else {
                                      listItemRefs.current.delete(chunk.index);
                                    }
                                  }}
                                  type="button"
                                  onClick={() => setSelectedIndex(chunk.index)}
                                  className={cx(
                                    "w-full px-3 py-2 text-left text-xs transition-colors",
                                    isSelected
                                      ? "bg-blue-50"
                                      : "bg-white hover:bg-gray-50",
                                  )}
                                  aria-pressed={isSelected}
                                  title={chunkMetaLine(chunk)}
                                >
                                  <div className="text-sm font-medium text-gray-800">
                                    {chunkTitle(chunk)}
                                  </div>
                                  <div className="mt-0.5 text-[11px] text-gray-400">
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

                    if (count === 0) {
                      return null;
                    }

                    return (
                      <div key={group.key}>
                        <button
                          type="button"
                          onClick={() => toggleGroup(group.key)}
                          className="flex w-full items-center justify-between gap-2 bg-gray-50 px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500"
                        >
                          <span className="flex items-center gap-2">
                            <span
                              className={cx(
                                "inline-flex h-4 w-4 items-center justify-center rounded border border-gray-300 bg-white text-[9px] leading-none text-gray-600",
                              )}
                            >
                              {isExpanded ? "−" : "+"}
                            </span>
                            {group.label}
                          </span>
                          <span className="text-[10px] font-normal text-gray-400">
                            {count}
                          </span>
                        </button>

                        {isExpanded && (
                          <div className="border-t border-gray-100">
                            {group.items.map((chunk) => {
                              const isSelected = selectedIndex === chunk.index;

                              return (
                                <button
                                  key={chunk.index}
                                  ref={(el) => {
                                    if (el) {
                                      listItemRefs.current.set(chunk.index, el);
                                    } else {
                                      listItemRefs.current.delete(chunk.index);
                                    }
                                  }}
                                  type="button"
                                  onClick={() => setSelectedIndex(chunk.index)}
                                  className={cx(
                                    "w-full px-3 py-2 text-left text-xs transition-colors",
                                    isSelected
                                      ? "bg-blue-50"
                                      : "bg-white hover:bg-gray-50",
                                  )}
                                  aria-pressed={isSelected}
                                  title={chunkMetaLine(chunk)}
                                >
                                  <div className="text-sm font-medium text-gray-800">
                                    {chunkTitle(chunk)}
                                  </div>
                                  <div className="mt-0.5 text-[11px] text-gray-400">
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
            <div className="px-3 py-3 text-sm text-gray-500">
              В v2-артефакте CHUNKS нет сегментов или чанков.
            </div>
          )}
        </div>
      </aside>

      {/* Средняя колонка: выбранный chunk */}
      <section className="min-h-0 min-w-0 overflow-hidden rounded-lg border border-gray-200 bg-white p-3">
        <div className="flex h-full min-h-0 flex-col overflow-hidden">
          <div className="mb-3 border-b border-gray-100 pb-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              Выбранный chunk
            </p>
            <p className="mt-1 text-xs text-gray-400">
              Canonical‑представление materialized chunks.
            </p>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {selectedChunk ? (
              <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
                <div>
                  <p className="text-sm font-semibold text-gray-900">
                    {chunkTitle(selectedChunk)}
                  </p>
                  <p className="mt-1 text-[11px] text-gray-400">
                    {chunkMetaLine(selectedChunk)}
                  </p>

                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500">
                    <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">
                      index: {selectedChunk.index}
                    </span>

                    {selectedChunk.clause_uid && (
                      <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">
                        clause_uid: {selectedChunk.clause_uid}
                      </span>
                    )}

                    {pageLabel(selectedChunk) !== "—" && (
                      <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">
                        pages: {pageLabel(selectedChunk)}
                      </span>
                    )}

                    {selectedChunk.segment_type && (
                      <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">
                        segment: {selectedChunk.segment_type}
                        {selectedChunk.is_primary_segment ? " (PRIMARY)" : ""}
                      </span>
                    )}

                    <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">
                      chars: {normalizeChunkText(selectedChunk.text).length}
                    </span>
                  </div>
                </div>

                <div className="rounded-md bg-gray-50 px-3 py-3">
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-500">
                    Текст chunk’а
                  </p>
                  <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-gray-700">
                    {normalizeChunkText(selectedChunk.text) || "—"}
                  </pre>
                </div>

                {reconstructedText ? (
                  <div className="rounded-md bg-gray-50 px-3 py-3">
                    <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-500">
                      Контекст stage
                    </p>
                    <p className="text-xs leading-5 text-gray-500">
                      Справа можно переключаться между JSON выбранного chunk’а и
                      полным snapshot этапа, прокручиваемым к этому chunk’у.
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-gray-500">
                Выбери chunk слева.
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Правая колонка: JSON chunk’а / JSON snapshot с переключателем */}
      <section className="min-h-0 min-w-0 overflow-hidden rounded-lg border border-gray-200 bg-white p-3">
        <div className="flex h-full min-h-0 flex-col">
          <div className="mb-3 flex min-h-[3.5rem] items-center justify-between gap-2 border-b border-gray-100 pb-2">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                {jsonMode === "chunk" ? "JSON chunk’а" : "JSON snapshot"}
              </p>
              <p className="mt-1 line-clamp-2 text-xs text-gray-400">
                {jsonMode === "chunk"
                  ? "Текущий объект materialized chunk’а из snapshot CHUNKS."
                  : "Полный canonical snapshot CHUNKS; выделен фрагмент текста выбранного chunk’а."}
              </p>
            </div>

            <div className="shrink-0 rounded-full bg-gray-100 px-1 py-0.5">
              <div className="flex items-center gap-0.5">
                <button
                  type="button"
                  onClick={() => setJsonMode("chunk")}
                  className={cx(
                    "rounded-full px-2 py-1 text-[11px] leading-none transition-colors",
                    jsonMode === "chunk"
                      ? "bg-gray-900 text-gray-100"
                      : "text-gray-600 hover:text-gray-900",
                  )}
                >
                  chunk
                </button>
                <button
                  type="button"
                  onClick={() => setJsonMode("snapshot")}
                  className={cx(
                    "rounded-full px-2 py-1 text-[11px] leading-none transition-colors",
                    jsonMode === "snapshot"
                      ? "bg-gray-900 text-gray-100"
                      : "text-gray-600 hover:text-gray-900",
                  )}
                >
                  snapshot
                </button>
              </div>
            </div>
          </div>

          {jsonMode === "chunk" ? (
            selectedChunk ? (
              <div className="min-h-0 flex-1 overflow-auto rounded-md bg-gray-950 p-3">
                <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-gray-100">
                  {chunkJson(selectedChunk)}
                </pre>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-gray-500">
                Выбери chunk слева.
              </div>
            )
          ) : (
            <div
              ref={snapshotRef}
              className="min-h-0 flex-1 overflow-auto rounded-md bg-gray-950 p-3"
            >
              <pre
                className="whitespace-pre-wrap break-words text-xs leading-5 text-gray-100"
                dangerouslySetInnerHTML={highlightedSnapshot}
              />
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default ChunksStageViewer;



