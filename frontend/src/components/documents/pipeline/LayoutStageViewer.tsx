// =============================================================
// src/components/documents/pipeline/LayoutStageViewer.tsx
// =============================================================

import React from "react";
import { FileText, Braces, Layers } from "lucide-react";
import type { LayoutPreviewDTO, PipelineStageViewDTO } from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

type TabKey = "view" | "json";

function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function MetaPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-1 text-[11px] leading-none text-[var(--text-secondary)]">
      {children}
    </span>
  );
}

/**
 * LayoutStageViewer
 *
 * Показывает layout-артефакт в двух вкладках:
 * - Просмотр: страницы и извлечённый текст;
 * - JSON: сырой payload артефакта.
 *
 * Название и описание стадии уже показаны в шапке модалки,
 * поэтому здесь мы не дублируем их повторно.
 */
export const LayoutStageViewer: React.FC<Props> = ({ stage }) => {
  const preview = stage.preview as LayoutPreviewDTO | null | undefined;
  const [tab, setTab] = React.useState<TabKey>("view");

  const tablistId = React.useId();
  const viewTabId = `${tablistId}-tab-view`;
  const jsonTabId = `${tablistId}-tab-json`;
  const viewPanelId = `${tablistId}-panel-view`;
  const jsonPanelId = `${tablistId}-panel-json`;

  if (!preview) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)] shadow-sm">
        Layout-превью недоступно.
      </div>
    );
  }

  const pages = Array.isArray(preview.pages) ? preview.pages : [];
  const jsonText = JSON.stringify(preview.raw_json ?? null, null, 2);
  const totalElements = pages.reduce(
    (sum, page) => sum + (page.element_count ?? 0),
    0,
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <MetaPill>
            <Layers size={12} className="mr-1" />
            Страниц: {pages.length}
          </MetaPill>
          <MetaPill>
            <FileText size={12} className="mr-1" />
            Элементов: {totalElements}
          </MetaPill>
        </div>

        <div
          role="tablist"
          aria-label="Режим просмотра layout-артефакта"
          className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-1"
        >
          <button
            id={viewTabId}
            type="button"
            role="tab"
            aria-selected={tab === "view"}
            aria-controls={viewPanelId}
            tabIndex={tab === "view" ? 0 : -1}
            onClick={() => setTab("view")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]",
              tab === "view"
                ? "bg-[var(--text-primary)] text-[var(--bg-card)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]",
            )}
          >
            <FileText size={14} />
            Просмотр
          </button>

          <button
            id={jsonTabId}
            type="button"
            role="tab"
            aria-selected={tab === "json"}
            aria-controls={jsonPanelId}
            tabIndex={tab === "json" ? 0 : -1}
            onClick={() => setTab("json")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]",
              tab === "json"
                ? "bg-[var(--text-primary)] text-[var(--bg-card)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]",
            )}
          >
            <Braces size={14} />
            JSON
          </button>
        </div>
      </div>

      {tab === "view" ? (
        <section
          id={viewPanelId}
          role="tabpanel"
          aria-labelledby={viewTabId}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {pages.length > 0 ? (
            <div className="space-y-3">
              {pages.map((page) => (
                <article
                  key={page.page}
                  className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 shadow-sm"
                >
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        Страница {page.page}
                      </p>
                      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                        Layout snapshot для страницы документа
                      </p>
                    </div>

                    <MetaPill>Элементов: {page.element_count}</MetaPill>
                  </div>

                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
                    <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
                      {page.text || "—"}
                    </pre>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 text-center">
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  Нет страниц для отображения
                </p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Layout-артефакт не содержит page preview для этого документа.
                </p>
              </div>
            </div>
          )}
        </section>
      ) : (
        <section
          id={jsonPanelId}
          role="tabpanel"
          aria-labelledby={jsonTabId}
          className="min-h-0 flex-1 overflow-hidden"
        >
          <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-inverse)] shadow-sm">
            <div className="border-b border-white/10 px-4 py-2">
              <p className="text-[11px] font-medium uppercase tracking-wide text-white/60">
                Raw payload
              </p>
            </div>

            <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words px-4 py-3 text-xs leading-5 text-[var(--text-inverse)]">
              {jsonText}
            </pre>
          </div>
        </section>
      )}
    </div>
  );
};

export default LayoutStageViewer;

