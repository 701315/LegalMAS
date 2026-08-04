// =============================================================
// src/components/documents/LayoutDebugModal.tsx
// Визуальное сравнение документа до и после PII-sanitation.
// =============================================================

import React, { useEffect, useMemo, useRef } from "react";
import { X, Loader2, AlertTriangle } from "lucide-react";
import { useDocumentLayoutsDebug } from "../../api/documents";
import Button from "../ui/Button";

interface Props {
  docId: string;
  isOpen: boolean;
  onClose: () => void;
}

type LayoutElement = {
  elementid?: string;
  text?: string;
  page?: number;
  bbox?: number[];
};

type LayoutPayload = {
  elements?: LayoutElement[];
};

type LayoutsDebugResponse = {
  documentid?: string;
  dealid?: string;
  rawlayoutref?: string | null;
  sanitizedlayoutref?: string | null;
  rawlayout?: LayoutPayload | null;
  sanitizedlayout?: LayoutPayload | null;

  // fallback camelCase
  documentId?: string;
  dealId?: string;
  rawLayoutRef?: string | null;
  sanitizedLayoutRef?: string | null;
  rawLayout?: LayoutPayload | null;
  sanitizedLayout?: LayoutPayload | null;
};

type CompareRow = {
  key: string;
  page: number;
  beforeText: string;
  afterText: string;
  changed: boolean;
  removed: boolean;
  added: boolean;
  matchType: "id" | "heuristic" | "removed" | "added";
};

type DiffToken =
  | { type: "same"; text: string }
  | { type: "changed"; text: string }
  | { type: "space"; text: string };

function isLayoutPayload(value: unknown): value is LayoutPayload {
  return !!value && typeof value === "object";
}

function normalizeText(text?: string): string {
  return (text || "").replace(/\s+/g, " ").trim();
}

function tokenizeForSimilarity(text: string): string[] {
  return normalizeText(text)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean);
}

function tokenizeWithSpaces(text: string): string[] {
  if (!text) return [];
  return text.match(/\S+|\s+/g) || [];
}

function isWhitespace(token: string): boolean {
  return /^\s+$/.test(token);
}

function normalizeWordForDiff(word: string): string {
  return word.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "").trim();
}

function textSimilarity(a: string, b: string): number {
  const aa = tokenizeForSimilarity(a);
  const bb = tokenizeForSimilarity(b);

  if (!aa.length && !bb.length) return 1;
  if (!aa.length || !bb.length) return 0;

  const setA = new Set(aa);
  const setB = new Set(bb);

  let intersection = 0;
  for (const token of setA) {
    if (setB.has(token)) intersection += 1;
  }

  const union = new Set([...setA, ...setB]).size;
  const jaccard = union === 0 ? 0 : intersection / union;

  const lenA = normalizeText(a).length;
  const lenB = normalizeText(b).length;
  const maxLen = Math.max(lenA, lenB, 1);
  const lenPenalty = 1 - Math.abs(lenA - lenB) / maxLen;

  return jaccard * 0.8 + Math.max(0, lenPenalty) * 0.2;
}

function sortElements(elements: LayoutElement[]): LayoutElement[] {
  return [...elements].sort((a, b) => {
    const ap = typeof a.page === "number" ? a.page : 0;
    const bp = typeof b.page === "number" ? b.page : 0;
    if (ap !== bp) return ap - bp;

    const ay = Array.isArray(a.bbox) ? (a.bbox[1] ?? 0) : 0;
    const by = Array.isArray(b.bbox) ? (b.bbox[1] ?? 0) : 0;
    if (Math.abs(ay - by) > 3) return ay - by;

    const ax = Array.isArray(a.bbox) ? (a.bbox[0] ?? 0) : 0;
    const bx = Array.isArray(b.bbox) ? (b.bbox[0] ?? 0) : 0;
    return ax - bx;
  });
}

function getElements(layout: unknown): LayoutElement[] {
  if (!isLayoutPayload(layout) || !Array.isArray(layout.elements)) return [];
  return sortElements(layout.elements);
}

function extractRawLayout(data: LayoutsDebugResponse | undefined): unknown {
  return data?.rawlayout ?? data?.rawLayout ?? null;
}

function extractSanitizedLayout(
  data: LayoutsDebugResponse | undefined,
): unknown {
  return data?.sanitizedlayout ?? data?.sanitizedLayout ?? null;
}

function buildCompareRows(
  rawLayout: unknown,
  sanitizedLayout: unknown,
): CompareRow[] {
  const rawElements = getElements(rawLayout);
  const sanitizedElements = getElements(sanitizedLayout);

  const rows: CompareRow[] = [];
  const usedSanitizedIndexes = new Set<number>();

  const sanitizedById = new Map<string, { el: LayoutElement; index: number }>();
  sanitizedElements.forEach((el, index) => {
    if (el.elementid) sanitizedById.set(el.elementid, { el, index });
  });

  const rawByPage = new Map<number, Array<{ el: LayoutElement; index: number }>>();
  const sanitizedByPage = new Map<
    number,
    Array<{ el: LayoutElement; index: number }>
  >();

  rawElements.forEach((el, index) => {
    const page = typeof el.page === "number" ? el.page : 1;
    if (!rawByPage.has(page)) rawByPage.set(page, []);
    rawByPage.get(page)!.push({ el, index });
  });

  sanitizedElements.forEach((el, index) => {
    const page = typeof el.page === "number" ? el.page : 1;
    if (!sanitizedByPage.has(page)) sanitizedByPage.set(page, []);
    sanitizedByPage.get(page)!.push({ el, index });
  });

  for (const [page, rawItems] of rawByPage.entries()) {
    const sanItems = sanitizedByPage.get(page) || [];

    for (const rawItem of rawItems) {
      const rawEl = rawItem.el;
      const rawText = normalizeText(rawEl.text);
      const key = rawEl.elementid || `raw-${page}-${rawItem.index}`;

      if (rawEl.elementid && sanitizedById.has(rawEl.elementid)) {
        const matched = sanitizedById.get(rawEl.elementid)!;
        const sanEl = matched.el;
        usedSanitizedIndexes.add(matched.index);

        const afterText = normalizeText(sanEl.text);

        rows.push({
          key,
          page,
          beforeText: rawText,
          afterText,
          changed: rawText !== afterText,
          removed: !!rawText && !afterText,
          added: false,
          matchType: "id",
        });
        continue;
      }

      let bestIndex = -1;
      let bestScore = 0;

      for (const sanItem of sanItems) {
        if (usedSanitizedIndexes.has(sanItem.index)) continue;

        const sanText = normalizeText(sanItem.el.text);
        if (!rawText && !sanText) continue;

        const score = textSimilarity(rawText, sanText);
        if (score > bestScore) {
          bestScore = score;
          bestIndex = sanItem.index;
        }
      }

      if (bestIndex >= 0 && bestScore >= 0.42) {
        usedSanitizedIndexes.add(bestIndex);
        const sanEl = sanitizedElements[bestIndex];
        const afterText = normalizeText(sanEl.text);

        rows.push({
          key,
          page,
          beforeText: rawText,
          afterText,
          changed: rawText !== afterText,
          removed: !!rawText && !afterText,
          added: false,
          matchType: "heuristic",
        });
      } else {
        rows.push({
          key,
          page,
          beforeText: rawText,
          afterText: "",
          changed: true,
          removed: true,
          added: false,
          matchType: "removed",
        });
      }
    }
  }

  sanitizedElements.forEach((sanEl, index) => {
    if (usedSanitizedIndexes.has(index)) return;

    const page = typeof sanEl.page === "number" ? sanEl.page : 1;

    rows.push({
      key: sanEl.elementid || `san-${page}-${index}`,
      page,
      beforeText: "",
      afterText: normalizeText(sanEl.text),
      changed: true,
      removed: false,
      added: true,
      matchType: "added",
    });
  });

  return rows.sort((a, b) => {
    if (a.page !== b.page) return a.page - b.page;
    return a.key.localeCompare(b.key);
  });
}

function groupRowsByPage(rows: CompareRow[]) {
  const map = new Map<number, CompareRow[]>();

  for (const row of rows) {
    if (!map.has(row.page)) map.set(row.page, []);
    map.get(row.page)!.push(row);
  }

  return Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([page, items]) => ({ page, items }));
}

function buildWordDiff(beforeText: string, afterText: string): DiffToken[] {
  if (!beforeText) return [];
  if (!afterText) return [{ type: "changed", text: beforeText }];

  const beforeTokens = tokenizeWithSpaces(beforeText);
  const afterTokens = tokenizeWithSpaces(afterText);

  const afterWordsNormalized = afterTokens
    .filter((t) => !isWhitespace(t))
    .map(normalizeWordForDiff)
    .filter(Boolean);

  const afterWordCounts = new Map<string, number>();
  for (const token of afterWordsNormalized) {
    afterWordCounts.set(token, (afterWordCounts.get(token) || 0) + 1);
  }

  const seenBeforeCounts = new Map<string, number>();
  const result: DiffToken[] = [];

  for (const token of beforeTokens) {
    if (isWhitespace(token)) {
      result.push({ type: "space", text: token });
      continue;
    }

    const normalized = normalizeWordForDiff(token);

    if (!normalized) {
      result.push({ type: "same", text: token });
      continue;
    }

    const seen = (seenBeforeCounts.get(normalized) || 0) + 1;
    seenBeforeCounts.set(normalized, seen);

    const available = afterWordCounts.get(normalized) || 0;

    if (seen <= available) {
      result.push({ type: "same", text: token });
    } else {
      result.push({ type: "changed", text: token });
    }
  }

  return result;
}

function MatchBadge({ type }: { type: CompareRow["matchType"] }) {
  const config =
    type === "id"
      ? {
          cls: "bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] border-[var(--border-subtle)]",
          text: "match: id",
        }
      : type === "heuristic"
        ? {
            cls: "bg-[var(--color-blue-highlight)] text-[var(--color-blue)] border-[var(--color-blue-strong)]/40",
            text: "match: similar text",
          }
        : type === "removed"
          ? {
              cls: "bg-[var(--color-error-bg)] text-[var(--color-error-text)] border-[var(--color-error-border)]",
              text: "removed",
            }
          : {
              cls: "bg-[var(--color-success-bg)] text-[var(--color-success-text)] border-[var(--color-success-border)]",
              text: "added",
            };

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px]",
        config.cls,
      ].join(" ")}
    >
      {config.text}
    </span>
  );
}

function BeforeTextDiff({
  beforeText,
  afterText,
  removed,
}: {
  beforeText: string;
  afterText: string;
  removed: boolean;
}) {
  if (!beforeText) {
    return (
      <span className="text-[var(--text-faint)] italic">Нет текста</span>
    );
  }

  if (removed) {
    return (
      <span className="rounded bg-[var(--color-error-bg)] px-1 py-0.5 text-[var(--color-error-text)]">
        {beforeText}
      </span>
    );
  }

  const tokens = buildWordDiff(beforeText, afterText);

  return (
    <>
      {tokens.map((token, index) => {
        if (token.type === "space") {
          return <React.Fragment key={index}>{token.text}</React.Fragment>;
        }

        if (token.type === "changed") {
          return (
            <span
              key={index}
              className="rounded bg-[var(--color-error-bg)] px-1 py-0.5 text-[var(--color-error-text)]"
            >
              {token.text}
            </span>
          );
        }

        return <React.Fragment key={index}>{token.text}</React.Fragment>;
      })}
    </>
  );
}

export const LayoutDebugModal: React.FC<Props> = ({
  docId,
  isOpen,
  onClose,
}) => {
  const {
    data,
    isLoading,
    error,
  } = useDocumentLayoutsDebug(isOpen ? docId : null, isOpen) as {
    data?: LayoutsDebugResponse;
    isLoading: boolean;
    error?: unknown;
  };

  const leftRef = useRef<HTMLDivElement | null>(null);
  const rightRef = useRef<HTMLDivElement | null>(null);
  const syncLockRef = useRef<"left" | "right" | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const rawLayout = useMemo(() => extractRawLayout(data), [data]);
  const sanitizedLayout = useMemo(
    () => extractSanitizedLayout(data),
    [data],
  );

  const groupedPages = useMemo(() => {
    const rows = buildCompareRows(rawLayout, sanitizedLayout);
    return groupRowsByPage(rows);
  }, [rawLayout, sanitizedLayout]);

  const handleSyncScroll = (source: "left" | "right") => {
    const left = leftRef.current;
    const right = rightRef.current;
    if (!left || !right) return;

    if (syncLockRef.current && syncLockRef.current !== source) return;

    syncLockRef.current = source;

    if (source === "left") {
      right.scrollTop = left.scrollTop;
    } else {
      left.scrollTop = right.scrollTop;
    }

    window.requestAnimationFrame(() => {
      syncLockRef.current = null;
    });
  };

  if (!isOpen) return null;

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) onClose();
  };

  const errorMessage =
    error instanceof Error
      ? error.message
      : error
        ? String(error)
        : "Неизвестная ошибка";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={handleBackdropClick}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="layout-compare-v3-title"
        className="flex h-[94vh] w-full max-w-[96vw] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-5 py-4">
          <div className="min-w-0">
            <h2
              id="layout-compare-v3-title"
              className="text-base font-semibold text-[var(--text-primary)]"
            >
              Документ до и после санитизации
            </h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              В левой колонке подсвечены только изменившиеся слова.
            </p>
          </div>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Закрыть"
            className="px-2 py-1 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            <X size={18} />
          </Button>
        </div>

        <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-5 py-3 text-xs text-[var(--text-secondary)]">
          Слева исходный текст, справа санитизированный. Если строка
          изменилась, в левой колонке подсвечиваются только изменённые
          слова; если строка удалена полностью, подсвечивается вся строка.
        </div>

        <div className="min-h-0 flex-1 bg-[var(--bg-elevated-soft)]">
          {isLoading && (
            <div className="flex h-full items-center justify-center bg-[var(--bg-card)] text-sm text-[var(--text-muted)]">
              <Loader2 className="mr-2 animate-spin" size={18} />
              Загрузка сравнения…
            </div>
          )}

          {!!error && !isLoading && (
            <div className="flex h-full flex-col items-center justify-center bg-[var(--bg-card)] text-center">
              <AlertTriangle
                size={20}
                className="mb-2 text-[var(--color-error-text)]"
              />
              <div className="text-sm font-medium text-[var(--color-error-text)]">
                Ошибка загрузки данных
              </div>
              <div className="mt-1 max-w-2xl break-all text-xs text-[var(--text-muted)]">
                {errorMessage}
              </div>
            </div>
          )}

          {!isLoading && !error && groupedPages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center bg-[var(--bg-card)] px-6 text-center text-sm text-[var(--text-muted)]">
              <div>Нет данных для сравнения raw / sanitized layout.</div>
              <div className="mt-2 text-xs text-[var(--text-faint)]">
                Проверь, что запрос debug-layouts вызывается с
                includeraw=true и includesanitized=true.
              </div>
            </div>
          )}

          {!isLoading && !error && groupedPages.length > 0 && (
            <div className="grid h-full grid-cols-1 gap-px bg-[var(--border-subtle)] lg:grid-cols-2">
              <div className="flex min-h-0 flex-col bg-[var(--bg-card)]">
                <div className="sticky top-0 z-10 border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    До санитизации
                  </div>
                </div>

                <div
                  ref={leftRef}
                  onScroll={() => handleSyncScroll("left")}
                  className="flex-1 space-y-6 overflow-auto px-4 py-4"
                >
                  {groupedPages.map((page) => (
                    <section
                      key={`left-page-${page.page}`}
                      className="space-y-3"
                    >
                      <div className="sticky top-0 z-[1] inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-1 text-xs text-[var(--text-muted)]">
                        Страница {page.page}
                      </div>

                      <div className="space-y-2">
                        {page.items.map((row) => (
                          <div
                            key={`left-${row.key}`}
                            className="rounded-md border border-transparent px-3 py-2"
                          >
                            <div className="mb-1 flex items-center gap-2">
                              <MatchBadge type={row.matchType} />
                            </div>

                            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-primary)]">
                              <BeforeTextDiff
                                beforeText={row.beforeText}
                                afterText={row.afterText}
                                removed={row.removed}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              </div>

              <div className="flex min-h-0 flex-col bg-[var(--bg-card)]">
                <div className="sticky top-0 z-10 border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 py-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    После санитизации
                  </div>
                </div>

                <div
                  ref={rightRef}
                  onScroll={() => handleSyncScroll("right")}
                  className="flex-1 space-y-6 overflow-auto px-4 py-4"
                >
                  {groupedPages.map((page) => (
                    <section
                      key={`right-page-${page.page}`}
                      className="space-y-3"
                    >
                      <div className="sticky top-0 z-[1] inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-1 text-xs text-[var(--text-muted)]">
                        Страница {page.page}
                      </div>

                      <div className="space-y-2">
                        {page.items.map((row) => (
                          <div
                            key={`right-${row.key}`}
                            className={
                              row.added
                                ? "rounded-md border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-3 py-2"
                                : "rounded-md border border-transparent bg-transparent px-3 py-2"
                            }
                          >
                            <div className="mb-1 flex items-center gap-2">
                              <MatchBadge type={row.matchType} />
                            </div>

                            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-primary)]">
                              {row.removed ? (
                                <span className="text-[var(--text-faint)] italic">
                                  Удалено после санитизации
                                </span>
                              ) : row.afterText ? (
                                row.afterText
                              ) : (
                                <span className="text-[var(--text-faint)] italic">
                                  Нет текста
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end border-t border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-5 py-3">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Закрыть
          </Button>
        </div>
      </div>
    </div>
  );
};

export default LayoutDebugModal;


