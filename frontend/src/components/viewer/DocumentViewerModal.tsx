// =============================================================
// src/components/viewer/DocumentViewerModal.tsx
//
// PDF viewer modal.
//
// Behavior:
// - Renders ALL pages of the PDF vertically inside the modal.
// - Auto-scrolls to `location.page` once the target page's geometry
//   is known (deterministic — no scrollIntoView timing guesses).
// - Lazy render: only pages near the viewport mount their <Page> canvas.
//   Placeholders keep the correct height so scroll never jumps.
// - Toolbar ◀ ▶ scroll smoothly to the previous / next page.
// - "visiblePage / numPages" updates as the user scrolls.
// - Anchor-target and chunk overlays render on their own pages.
// =============================================================

import React from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { useTranslation } from "react-i18next";
import type { OpenViewerAtPayload } from "../../types";

// Explicit worker path from pdfjs-dist
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export interface LayoutElement {
  elementId: string;
  page: number;
  bbox: [number, number, number, number];
}

export interface SizedChunkMeta {
  id: string;
  elementIds: string[];
  clauseUids: string[];
  // Human-readable number, e.g. "6.3" / "1" — fallback match
  // when clauseUid is missing (per_field LLM не возвращает uid).
  rawUids: string[];
}

interface DocumentViewerModalProps {
  open: boolean;
  onClose: () => void;
  fileUrl: string | null;
  location: OpenViewerAtPayload | null;
  initialScale?: number;
  title?: string | null;
  layoutElements?: LayoutElement[];
  sizedChunks?: SizedChunkMeta[];
}

type PageSize = {
  originalWidth: number;
  originalHeight: number;
};

type PageRenderInfo = {
  originalWidth?: number;
  originalHeight?: number;
};

// Visual spacing between stacked page wrappers, in CSS pixels.
// Used by both the DOM layout (marginBottom) and the scrollTop
// arithmetic in scrollToPage — keep them in sync via this constant.
const PAGE_GAP_PX = 12;

// IntersectionObserver rootMargin for lazy page rendering.
// 1000px ≈ one viewport height of buffer above/below visible area.
const LAZY_RENDER_MARGIN_PX = 1000;

// Number of concurrent getPage() calls in the metadata pre-fetch phase.
// Bounds the pdfjs-worker queue; keeps memory and CPU predictable for
// large documents (hundreds of pages) without adding user-visible delay.
const METADATA_CHUNK_SIZE = 20;

/**
 * Pre-fetch original (unscaled) dimensions for every page of the PDF.
 *
 * Runs getPage()/getViewport() in chunks so a 500-page document does not
 * fire 500 concurrent worker tasks. getViewport({ scale: 1 }) is a
 * synchronous metadata read — no canvas is rasterised.
 */
async function loadPageSizesChunked(
  pdf: PDFDocumentProxy,
): Promise<Map<number, PageSize>> {
  const sizes = new Map<number, PageSize>();
  const total = pdf.numPages;
  for (let start = 1; start <= total; start += METADATA_CHUNK_SIZE) {
    const end = Math.min(start + METADATA_CHUNK_SIZE - 1, total);
    await Promise.all(
      Array.from({ length: end - start + 1 }, async (_, i) => {
        const pageNum = start + i;
        try {
          const page = await pdf.getPage(pageNum);
          const viewport = page.getViewport({ scale: 1 });
          sizes.set(pageNum, {
            originalWidth: viewport.width,
            originalHeight: viewport.height,
          });
        } catch {
          // Non-fatal: onRenderSuccess will backfill the size later.
        }
      }),
    );
  }
  return sizes;
}

const DocumentViewerModal: React.FC<DocumentViewerModalProps> = ({
  open,
  onClose,
  fileUrl,
  location,
  initialScale = 0.9,
  title,
  layoutElements,
  sizedChunks,
}) => {
  const { t } = useTranslation("documents");

  const [numPages, setNumPages] = React.useState<number | null>(null);
  // visiblePage is initialized from the incoming location and reset by
  // the parent when `location` changes (parent applies a `key` to this
  // component, causing a remount). This avoids a setState-in-effect
  // that would otherwise trigger a cascading render on every location
  // update — see react-hooks/set-state-in-effect.
  const initialVisiblePage =
    location?.page && location.page > 0 ? location.page : 1;
  const [visiblePage, setVisiblePage] =
    React.useState<number>(initialVisiblePage);
  const [pageSizes, setPageSizes] = React.useState<Map<number, PageSize>>(
    () => new Map(),
  );
  const [shouldRenderPages, setShouldRenderPages] = React.useState<
    Set<number>
  >(() => new Set());
  const [containerWidth, setContainerWidth] = React.useState<number | null>(
    null,
  );

  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const pageRefs = React.useRef<Map<number, HTMLDivElement>>(new Map());
  const observerRef = React.useRef<IntersectionObserver | null>(null);
  const programmaticScrollRef = React.useRef(false);
  const rafHandleRef = React.useRef<number | null>(null);

  // Track container width for responsive page sizing.
  React.useLayoutEffect(() => {
    if (!open) return;

    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.clientWidth);
      }
    };

    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => {
      window.removeEventListener("resize", updateWidth);
    };
  }, [open]);

  // ESC to close.
  React.useEffect(() => {
    if (!open) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Cleanup RAF handle on unmount.
  React.useEffect(() => {
    return () => {
      if (rafHandleRef.current != null) {
        window.cancelAnimationFrame(rafHandleRef.current);
        rafHandleRef.current = null;
      }
    };
  }, []);

  const pageWidth = (containerWidth ?? 900) * initialScale;

  // Deterministic scroll to a specific page. Uses exact arithmetic on
  // scaled page heights; falls back to scrollIntoView only when the
  // preceding page sizes are not yet known.
  const scrollToPage = (
    target: number,
    options: { behavior?: ScrollBehavior } = {},
  ) => {
    if (!numPages) return;
    const clamped = Math.min(Math.max(target, 1), numPages);
    const container = containerRef.current;
    if (!container) return;

    const behavior = options.behavior ?? "smooth";

    let y: number;
    if (clamped === 1) {
      y = 0;
    } else {
      const allBeforeKnown = Array.from(
        { length: clamped - 1 },
        (_, i) => i + 1,
      ).every((p) => pageSizes.has(p));
      if (!allBeforeKnown) {
        const el = pageRefs.current.get(clamped);
        if (!el) return;
        programmaticScrollRef.current = true;
        el.scrollIntoView({ block: "start", behavior });
        setVisiblePage(clamped);
        window.setTimeout(() => {
          programmaticScrollRef.current = false;
        }, 600);
        return;
      }
      y = 0;
      for (let p = 1; p < clamped; p++) {
        const size = pageSizes.get(p)!;
        const scaled = size.originalHeight * (pageWidth / size.originalWidth);
        y += scaled + PAGE_GAP_PX;
      }
    }

    programmaticScrollRef.current = true;
    container.scrollTo({ top: y, behavior });
    setVisiblePage(clamped);
    window.setTimeout(() => {
      programmaticScrollRef.current = false;
    }, 600);
  };

  // Deterministic auto-scroll once all page sizes up to `location.page`
  // are available. Depends on pageSizes.size (a primitive), so it fires
  // exactly when a new chunk of metadata lands.
  React.useEffect(() => {
    if (!open || !numPages) return;
    const targetRaw = location?.page;
    const target = Math.min(
      Math.max(targetRaw && targetRaw > 0 ? targetRaw : 1, 1),
      numPages,
    );

    const allReady = Array.from({ length: target }, (_, i) => i + 1).every(
      (p) => pageSizes.has(p),
    );
    if (!allReady) return;

    // scrollToPage performs a DOM side-effect and updates visiblePage.
    // The setState is intentional: the toolbar counter must reflect the
    // target page immediately after auto-scroll on open. Reset-on-location
    // is handled by the parent via a `key` on this component (remount),
    // so no state-sync effect is needed.
    /* eslint-disable-next-line react-hooks/set-state-in-effect --
       intentional sync between programmatic scroll and toolbar counter */
    scrollToPage(target, { behavior: "auto" });
    /* eslint-disable-next-line react-hooks/exhaustive-deps --
       full deps list would include pageSizes.has / scrollToPage, both
       stable for this effect's purpose; pageSizes.size tracks metadata
       arrival and location?.page covers target changes */
  }, [open, numPages, location?.page, fileUrl, pageSizes.size]);

  // Lazy render: observe all page wrappers, render <Page> only for
  // pages that enter the expanded viewport buffer.
  React.useEffect(() => {
    if (!open || !numPages) return;

    const observer = new IntersectionObserver(
      (entries) => {
        let changed = false;
        setShouldRenderPages((prev) => {
          const next = new Set(prev);
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              const raw = (entry.target as HTMLElement).dataset.pageNumber;
              const pageNum = Number(raw);
              if (Number.isFinite(pageNum) && !next.has(pageNum)) {
                next.add(pageNum);
                changed = true;
              }
            }
          });
          return changed ? next : prev;
        });
      },
      {
        root: containerRef.current,
        rootMargin: `${LAZY_RENDER_MARGIN_PX}px 0px`,
        threshold: 0,
      },
    );

    observerRef.current = observer;
    pageRefs.current.forEach((el) => observer.observe(el));

    return () => {
      observer.disconnect();
      observerRef.current = null;
    };
  }, [open, numPages]);

  if (!open) return null;

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleDocumentLoad = async (pdf: PDFDocumentProxy) => {
    setNumPages(pdf.numPages);
    const sizes = await loadPageSizesChunked(pdf);
    setPageSizes((prev) => {
      const next = new Map(prev);
      sizes.forEach((v, k) => next.set(k, v));
      return next;
    });
  };

  const handlePageRenderSuccess = (
    pageNum: number,
    info: PageRenderInfo,
  ) => {
    if (
      typeof info.originalWidth !== "number" ||
      typeof info.originalHeight !== "number"
    ) {
      return;
    }
    setPageSizes((prev) => {
      const existing = prev.get(pageNum);
      if (
        existing &&
        existing.originalWidth === info.originalWidth &&
        existing.originalHeight === info.originalHeight
      ) {
        return prev;
      }
      const next = new Map(prev);
      next.set(pageNum, {
        originalWidth: info.originalWidth as number,
        originalHeight: info.originalHeight as number,
      });
      return next;
    });
  };

  const handlePrevPage = () => scrollToPage(visiblePage - 1);
  const handleNextPage = () => scrollToPage(visiblePage + 1);

  const handleContainerScroll = () => {
    if (programmaticScrollRef.current) return;
    if (rafHandleRef.current != null) return;
    rafHandleRef.current = window.requestAnimationFrame(() => {
      rafHandleRef.current = null;
      const container = containerRef.current;
      if (!container) return;
      const containerTop = container.getBoundingClientRect().top;
      let bestPage = visiblePage;
      let bestDistance = Number.POSITIVE_INFINITY;
      pageRefs.current.forEach((el, pageNum) => {
        const rect = el.getBoundingClientRect();
        const distance = Math.abs(rect.top - containerTop);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestPage = pageNum;
        }
      });
      if (bestPage !== visiblePage) {
        setVisiblePage(bestPage);
      }
    });
  };

  const headerTitle =
    title ||
    (location?.documentId
      ? t("viewer.documentIdTitle", { id: location.documentId })
      : t("viewer.defaultTitle"));

  const lowerTitle = (title ?? "").toLowerCase();
  const hasErrorTitle = Boolean(
    lowerTitle.includes("error") ||
      lowerTitle.includes("\u043e\u0448\u0438\u0431\u043a"),
  );
  const isLoadingTitle = Boolean(
    lowerTitle.includes("load") ||
      lowerTitle.includes("\u0437\u0430\u0433\u0440\u0443\u0437\u043a"),
  );

  let activeChunkIndex = -1;

  if (sizedChunks && sizedChunks.length > 0 && location) {
    const { chunkId, chunkIndex, clauseUid } = location;

    if (chunkId) {
      const idx = sizedChunks.findIndex((ch) => ch.id === chunkId);
      if (idx >= 0) {
        activeChunkIndex = idx;
      }
    }

    if (
      activeChunkIndex < 0 &&
      typeof chunkIndex === "number" &&
      chunkIndex >= 0 &&
      chunkIndex < sizedChunks.length
    ) {
      activeChunkIndex = chunkIndex;
    }

    if (activeChunkIndex < 0 && clauseUid) {
      const idx = sizedChunks.findIndex((ch) =>
        ch.clauseUids?.includes(clauseUid),
      );
      if (idx >= 0) {
        activeChunkIndex = idx;
      }
    }
  }

  const elementToChunkIndex = (() => {
    const map = new Map<string, number>();
    (sizedChunks ?? []).forEach((chunk, chunkIndex) => {
      (chunk.elementIds ?? []).forEach((elId) => {
        if (elId) {
          map.set(elId, chunkIndex);
        }
      });
    });
    return map;
  })();

  // B5: anchor-target set из payload. Непусто → подсветка элементов
  // напрямую, даже без chunkIndex. Пусто → fallback на chunk-bbox.
  const anchorTargetElementIds = new Set(location?.layoutElementIds ?? []);

  // ── Chunk-level fallback по clauseUid ────────────────────────────────
  // Backend anchor (layoutElementIds) для canonical_check указывает на
  // элементы сегмента («где искали», обычно не на целевом пункте).
  // Реальное место находки можно восстановить через sizedChunks:
  // clauseUid ↔ chunk.clauseUids → chunk.elementIds (точные элементы).
  //
  // Проверено на liability_sanctions:
  //   clause_uid = 'main_contract:6.3'
  //   chunk.main_contract:6.3 → element_ids на page 4
  //   backend anchor → element на page 5 (неверно)
  //
  // Fallback не влияет на per_field случаи — они уже работают через
  // layoutElementIds.
  const clauseFallbackElementIds = (() => {
    if (!sizedChunks?.length) return null;
    const ids = new Set<string>();

    // Приоритет 1: exact clauseUid match.
    const clauseUid = location?.clauseUid;
    if (clauseUid) {
      for (const chunk of sizedChunks) {
        if (chunk.clauseUids?.includes(clauseUid)) {
          (chunk.elementIds ?? []).forEach((id) => ids.add(id));
        }
      }
    }

    // Приоритет 2: extract number from clauseRef ("п. 1" / "cl. 6.3")
    // → match chunk.rawUids. Используется когда per_field LLM вернула
    // только clause_ref без clause_uid (top-level uid = retrieval rank-0,
    // не место находки).
    if (ids.size === 0) {
      const ref = location?.clauseRef;
      if (ref) {
        const num = ref
          .replace(/^(cl\.|п\.|clause\s+|section\s+)\s*/i, "")
          .trim();
        if (num) {
          for (const chunk of sizedChunks) {
            if (chunk.rawUids?.includes(num)) {
              (chunk.elementIds ?? []).forEach((id) => ids.add(id));
            }
          }
        }
      }
    }

    return ids.size > 0 ? ids : null;
  })();

  const overlaysForPage = (pageNum: number) => {
    if (!layoutElements || layoutElements.length === 0) return [];
    return layoutElements
      .filter((el) => el.page === pageNum)
      .map((el) => ({
        bbox: el.bbox,
        chunkIndex: elementToChunkIndex.get(el.elementId) ?? null,
        // Приоритет: backend anchor → chunk-level fallback по clauseUid.
        isAnchorTarget:
          anchorTargetElementIds.has(el.elementId) ||
          (clauseFallbackElementIds?.has(el.elementId) ?? false),
      }));
  };

  const metadataReady = numPages != null && pageSizes.size >= numPages;

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/65"
      onClick={handleBackdropClick}
    >
      <div
        className="flex h-[95vh] w-[95vw] max-w-6xl flex-col rounded-[28px] border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label={t("viewer.ariaLabel")}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border-soft)] px-4 py-2 text-xs">
          <div className="flex flex-col">
            <span
              className={
                "max-w-[360px] truncate " +
                (hasErrorTitle
                  ? "font-medium text-[var(--color-error-text)]"
                  : isLoadingTitle
                    ? "font-medium text-[var(--text-secondary)]"
                    : "font-medium text-[var(--text-primary)]")
              }
            >
              {headerTitle}
            </span>
            <span className="text-[11px] text-[var(--text-muted)]">
              {location?.page
                ? t("viewer.pageLabel", { page: location.page })
                : t("viewer.pageDefault")}
              {location?.clauseUid &&
                ` · ${t("viewer.clauseLabel", { clause: location.clauseUid })}`}
            </span>
          </div>
          <button
            type="button"
            className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-3 py-1 text-[11px] text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
            onClick={onClose}
          >
            {t("viewer.closeBtn")}
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-2 text-[11px] text-[var(--text-secondary)]">
          <div className="flex items-center gap-2">
            <span>{t("viewer.navLabel")}</span>
            <button
              type="button"
              className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-1 transition hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-40"
              onClick={handlePrevPage}
              disabled={visiblePage <= 1}
            >
              ◀
            </button>
            <span>
              {numPages
                ? t("viewer.pageOf", {
                    current: visiblePage,
                    total: numPages,
                  })
                : t("viewer.pageCurrent", { current: visiblePage })}
            </span>
            <button
              type="button"
              className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-1 transition hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-40"
              onClick={handleNextPage}
              disabled={!numPages || visiblePage >= numPages}
            >
              ▶
            </button>
          </div>
          <div className="text-[11px] text-[var(--text-muted)]">
            {t("viewer.exitHint")}
          </div>
        </div>

        {/* Body */}
        <div
          ref={containerRef}
          onScroll={handleContainerScroll}
          className="flex flex-1 justify-center overflow-auto bg-[var(--bg-base)] p-3"
        >
          {!fileUrl ? (
            <div className="rounded-[16px] bg-[var(--bg-card)] px-4 py-3 text-xs text-[var(--color-error-text)]">
              {t("viewer.noPdfUrl")}
            </div>
          ) : (
            <Document
              file={fileUrl}
              onLoadSuccess={handleDocumentLoad}
              loading={
                <div className="rounded-[16px] bg-[var(--bg-card)] px-4 py-3 text-xs text-[var(--text-secondary)]">
                  {t("viewer.loadingPdf")}
                </div>
              }
              error={
                <div className="rounded-[16px] bg-[var(--bg-card)] px-4 py-3 text-xs text-[var(--color-error-text)]">
                  {t("viewer.loadError")}
                </div>
              }
            >
              {!metadataReady ? (
                <div className="rounded-[16px] bg-[var(--bg-card)] px-4 py-3 text-xs text-[var(--text-secondary)]">
                  {t("viewer.loadingPages")}
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  {Array.from({ length: numPages ?? 0 }, (_, i) => {
                    const pageNum = i + 1;
                    const size = pageSizes.get(pageNum);
                    if (!size) return null;
                    const scaledHeight =
                      size.originalHeight * (pageWidth / size.originalWidth);
                    const overlays = overlaysForPage(pageNum);
                    const renderCanvas = shouldRenderPages.has(pageNum);

                    return (
                      <div
                        key={pageNum}
                        data-page-number={pageNum}
                        ref={(el) => {
                          if (el) {
                            pageRefs.current.set(pageNum, el);
                            if (observerRef.current) {
                              observerRef.current.observe(el);
                            }
                          } else {
                            const existing = pageRefs.current.get(pageNum);
                            if (existing && observerRef.current) {
                              observerRef.current.unobserve(existing);
                            }
                            pageRefs.current.delete(pageNum);
                          }
                        }}
                        className="relative bg-[var(--bg-elevated-soft)]"
                        style={{
                          width: pageWidth,
                          height: scaledHeight,
                          marginBottom: PAGE_GAP_PX,
                        }}
                      >
                        {renderCanvas && (
                          <Page
                            pageNumber={pageNum}
                            width={pageWidth}
                            onRenderSuccess={(info) =>
                              handlePageRenderSuccess(pageNum, info)
                            }
                          />
                        )}
                        {overlays.length > 0 && (
                          <div className="pointer-events-none absolute inset-0">
                            {overlays.map((ov, idx) => {
                              // B5: anchor target рендерится даже без
                              // chunkIndex.
                              if (
                                ov.chunkIndex == null &&
                                !ov.isAnchorTarget
                              ) {
                                return null;
                              }

                              const [x0, top, x1, bottom] = ov.bbox;

                              const scaleX = pageWidth / size.originalWidth;

                              const left = x0 * scaleX;
                              const width = (x1 - x0) * scaleX;
                              const y = top * scaleX;
                              const height = (bottom - top) * scaleX;

                              const isActive =
                                activeChunkIndex >= 0 &&
                                ov.chunkIndex === activeChunkIndex;

                              // Только anchor или active chunk. Декоративная
                              // полосатость chunks убрана: пользователь принимал
                              // её за подсветку anchor'а.
                              const bgClass = ov.isAnchorTarget
                                ? "bg-[var(--accent-primary)]/28 ring-2 ring-[var(--accent-primary)]"
                                : isActive
                                  ? "bg-[var(--accent-primary)]/18 ring-2 ring-[var(--accent-primary)]/80"
                                  : "";

                              return (
                                <div
                                  key={idx}
                                  className={bgClass}
                                  data-active-overlay={
                                    isActive ? "true" : undefined
                                  }
                                  style={{
                                    position: "absolute",
                                    left,
                                    top: y,
                                    width,
                                    height,
                                  }}
                                />
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </Document>
          )}
        </div>
      </div>
    </div>
  );
};

export default DocumentViewerModal;
