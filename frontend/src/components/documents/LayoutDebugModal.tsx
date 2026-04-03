/**
 * LayoutDebugModal
 *
 * Визуальное сравнение документа до и после PII-sanitation.
 *
 * Что делает:
 * - показывает две синхронно прокручиваемые колонки;
 * - слева отображает raw layout (исходный текст);
 * - справа отображает sanitized layout (текст после санитизации);
 * - сопоставляет строки сначала по elementid, затем эвристически по похожести текста внутри страницы;
 * - в левой колонке подсвечивает только изменившиеся слова внутри строки;
 * - если строка удалена полностью, подсвечивает весь исходный текст как удалённый.
 *
 * Для чего нужен:
 * - быстро проверить, как именно изменился документ после санитизации;
 * - понять, какие слова были замаскированы, заменены или удалены;
 * - визуально валидировать результат PII pipeline без чтения JSON.
 *
 * Важно:
 * - backend debug endpoint возвращает raw/sanitized JSON только если включены
 *   query params includeraw=true и includesanitized=true;
 * - этот компонент предполагает, что useDocumentLayoutsDebug делает именно такой запрос.
 */

import React, { useEffect, useMemo, useRef } from "react";
import { X, Loader2, AlertTriangle } from "lucide-react";
import { useDocumentLayoutsDebug } from "../../api/documents";

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

  // fallback for camelCase if frontend mapper normalizes keys
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

function extractSanitizedLayout(data: LayoutsDebugResponse | undefined): unknown {
  return data?.sanitizedlayout ?? data?.sanitizedLayout ?? null;
}

function buildCompareRows(rawLayout: unknown, sanitizedLayout: unknown): CompareRow[] {
  const rawElements = getElements(rawLayout);
  const sanitizedElements = getElements(sanitizedLayout);

  const rows: CompareRow[] = [];
  const usedSanitizedIndexes = new Set<number>();

  const sanitizedById = new Map<string, { el: LayoutElement; index: number }>();
  sanitizedElements.forEach((el, index) => {
    if (el.elementid) sanitizedById.set(el.elementid, { el, index });
  });

  const rawByPage = new Map<number, Array<{ el: LayoutElement; index: number }>>();
  const sanitizedByPage = new Map<number, Array<{ el: LayoutElement; index: number }>>();

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
          cls: "bg-gray-100 text-gray-700 border-gray-200",
          text: "match: id",
        }
      : type === "heuristic"
        ? {
            cls: "bg-blue-100 text-blue-700 border-blue-200",
            text: "match: similar text",
          }
        : type === "removed"
          ? {
              cls: "bg-red-100 text-red-700 border-red-200",
              text: "removed",
            }
          : {
              cls: "bg-emerald-100 text-emerald-700 border-emerald-200",
              text: "added",
            };

  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] ${config.cls}`}>
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
    return <span className="text-gray-400 italic">Нет текста</span>;
  }

  if (removed) {
    return (
      <span className="rounded px-1 py-0.5 bg-red-100 text-red-900">
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
              className="rounded px-1 py-0.5 bg-red-100 text-red-900"
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

export const LayoutDebugModal: React.FC<Props> = ({ docId, isOpen, onClose }) => {
  /**
   * Важно:
   * backend endpoint /documents/{docId}/debug-layouts по умолчанию НЕ включает raw/sanitized JSON,
   * если не передать includeraw=true и includesanitized=true.
   *
   * Этот вызов предполагает, что хук useDocumentLayoutsDebug внутри себя делает запрос именно так.
   * Если хук этого не делает — ниже в UI ты увидишь "Нет данных для сравнения".
   */
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

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const rawLayout = useMemo(() => extractRawLayout(data), [data]);
  const sanitizedLayout = useMemo(() => extractSanitizedLayout(data), [data]);

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

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const errorMessage =
    error instanceof Error ? error.message : error ? String(error) : "Неизвестная ошибка";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={handleBackdropClick}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="layout-compare-v3-title"
        className="w-full max-w-[96vw] h-[94vh] rounded-xl bg-white shadow-2xl border border-gray-200 flex flex-col overflow-hidden"
      >
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b bg-gray-50">
          <div className="min-w-0">
            <h2
              id="layout-compare-v3-title"
              className="text-base font-semibold text-gray-900"
            >
              Документ до и после санитизации
            </h2>
            <p className="text-xs text-gray-500 mt-1 break-all">
              В левой колонке подсвечены только изменившиеся слова
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-md text-gray-500 hover:bg-gray-200 hover:text-gray-700"
            aria-label="Закрыть"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-3 border-b bg-white text-sm text-gray-700">
          Слева исходный текст, справа санитизированный. Если строка изменилась, в левой колонке подсвечиваются только изменённые слова; если строка удалена полностью, подсвечивается вся строка.
        </div>

        <div className="flex-1 min-h-0 bg-gray-100">
          {isLoading && (
            <div className="h-full flex items-center justify-center text-sm text-gray-500 bg-white">
              <Loader2 className="animate-spin mr-2" size={18} />
              Загрузка сравнения…
            </div>
          )}

          {!!error && !isLoading && (
            <div className="h-full flex flex-col items-center justify-center text-center bg-white">
              <AlertTriangle size={20} className="mb-2 text-red-500" />
              <div className="text-sm font-medium text-red-700">
                Ошибка загрузки данных
              </div>
              <div className="mt-1 text-xs text-gray-500 break-all max-w-2xl">
                {errorMessage}
              </div>
            </div>
          )}

          {!isLoading && !error && groupedPages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center text-sm text-gray-500 bg-white px-6">
              <div>Нет данных для сравнения raw / sanitized layout.</div>
              <div className="mt-2 text-xs text-gray-400">
                Проверь, что запрос debug-layouts вызывается с includeraw=true и includesanitized=true.
              </div>
            </div>
          )}

          {!isLoading && !error && groupedPages.length > 0 && (
            <div className="h-full grid grid-cols-1 lg:grid-cols-2 gap-px bg-gray-200">
              <div className="min-h-0 bg-white flex flex-col">
                <div className="sticky top-0 z-10 px-4 py-3 border-b bg-white">
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                    До санитизации
                  </div>
                </div>

                <div
                  ref={leftRef}
                  onScroll={() => handleSyncScroll("left")}
                  className="flex-1 overflow-auto px-4 py-4 space-y-6"
                >
                  {groupedPages.map((page) => (
                    <section key={`left-page-${page.page}`} className="space-y-3">
                      <div className="sticky top-0 z-[1] inline-flex text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                        Страница {page.page}
                      </div>

                      <div className="space-y-2">
                        {page.items.map((row) => (
                          <div
                            key={`left-${row.key}`}
                            className="rounded-md px-3 py-2 border border-transparent"
                          >
                            <div className="flex items-center gap-2 mb-1">
                              <MatchBadge type={row.matchType} />
                            </div>

                            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-900">
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

              <div className="min-h-0 bg-white flex flex-col">
                <div className="sticky top-0 z-10 px-4 py-3 border-b bg-white">
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                    После санитизации
                  </div>
                </div>

                <div
                  ref={rightRef}
                  onScroll={() => handleSyncScroll("right")}
                  className="flex-1 overflow-auto px-4 py-4 space-y-6"
                >
                  {groupedPages.map((page) => (
                    <section key={`right-page-${page.page}`} className="space-y-3">
                      <div className="sticky top-0 z-[1] inline-flex text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                        Страница {page.page}
                      </div>

                      <div className="space-y-2">
                        {page.items.map((row) => (
                          <div
                            key={`right-${row.key}`}
                            className={
                              row.added
                                ? "rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2"
                                : "rounded-md border border-transparent bg-transparent px-3 py-2"
                            }
                          >
                            <div className="flex items-center gap-2 mb-1">
                              <MatchBadge type={row.matchType} />
                            </div>

                            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-900">
                              {row.removed ? (
                                <span className="text-gray-400 italic">
                                  Удалено после санитизации
                                </span>
                              ) : row.afterText ? (
                                row.afterText
                              ) : (
                                <span className="text-gray-400 italic">Нет текста</span>
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

        <div className="px-5 py-3 border-t bg-gray-50 flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-3 py-2 text-xs rounded-md bg-gray-900 text-white hover:bg-gray-800"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

export default LayoutDebugModal;

