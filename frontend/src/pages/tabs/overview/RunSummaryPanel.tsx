// =============================================================
// src/pages/tabs/overview/RunSummaryPanel.tsx
// Panel displaying analysis run summary and insights.
// =============================================================

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  FileText,
  RefreshCw,
  AlertCircle,
  ChevronRight,
  X,
  Check,
} from "lucide-react";
import type { RunSummaryResponse } from "../../../api/runs";
import type { DocumentListItem } from "../../../types";
import { regenerateRunSummary } from "../../../api/runs";
import Button from "../../../components/ui/Button";
import InlineAlert from "../../../components/InlineAlert";

interface RunSummaryPanelProps {
  summary: RunSummaryResponse;
  onRegenerate: () => void;
  onClose?: () => void;
  isRail?: boolean;
  documents?: DocumentListItem[];
  dealId: string;
}

/**
 * Normalizes LLM summary text.
 * LLMs often return list items as a single inline block: "* Header * Item1 * Item2".
 * This helper prepends newlines before list markers and after emoji headings.
 */
const normalizeSummaryText = (raw: string): string => {
  if (!raw) return "";

  let text = raw.replace(/\r\n/g, "\n");

  // Remove markdown bold formatting
  text = text.replace(/\*\*/g, "");

  // Completely strip out all markdown headers
  text = text.replace(/#{1,6}\s*/g, "");

  // Prepend newline before list markers (" * " or " - ") when located mid-line
  text = text.replace(/\s+\*\s+/g, "\n* ");
  text = text.replace(/\s+-\s+/g, "\n- ");

  // Prepend newline before numbered lists mid-line
  text = text.replace(/\s+(\d+)\.\s+/g, "\n$1. ");

  // Emoji headings are placed on separate lines and marked with §H§ internally
  text = text.replace(
    /([🔴🟠🟡🟢✅📊⚠️📌])\s*([^\n*\-]+?)(?=\s*[\n*\-]|$)/gu,
    (_m, emoji, title) => {
      const cleanTitle = title.trim().replace(/[:：]\s*$/, "");
      return `\n\n§H§${emoji} ${cleanTitle}\n`;
    },
  );

  // Collapse duplicate consecutive empty lines
  text = text.replace(/\n{3,}/g, "\n\n");

  return text.trim();
};

export const RunSummaryPanel: React.FC<RunSummaryPanelProps> = ({
  summary,
  onRegenerate,
  onClose,
  isRail = false,
  documents,
  dealId,
}) => {
  const { t, i18n } = useTranslation("projects");
  const navigate = useNavigate();
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

  const handleRegenerate = async () => {
    setIsRegenerating(true);
    try {
      await regenerateRunSummary(summary.run_id);
      onRegenerate();
    } catch (err) {
      console.error("Regeneration failed", err);
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleCopyText = async () => {
    try {
      if (!summary.text) return;
      await navigator.clipboard.writeText(summary.text);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (err) {
      console.error("Copy failed:", err);
      alert(t("overviewPanels.runSummary.copyFailed"));
    }
  };

  // Wraps check IDs into interactive links
  const renderCitations = (text: string) => {
    const parts = text.split(/(\[[^\]]+\])/g);
    return parts.map((part, i) => {
      const match = part.match(/^\[([^\]]+)\]$/);
      if (match) {
        const checkId = match[1];
        return (
          <button
            key={i}
            type="button"
            onClick={() =>
              navigate(`/projects/${dealId}?tab=dd_grid&check=${checkId}`)
            }
            className="inline-flex items-center gap-0.5 text-[var(--accent-primary)] hover:underline font-medium mx-0.5 align-baseline"
            title={t("overviewPanels.runSummary.goToCheck")}
          >
            {part}
            <ChevronRight size={11} />
          </button>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  /**
   * Main renderer: parses normalized text into blocks,
   * combining consecutive list items into single lists.
   */
  const renderFormattedSummary = (rawText: string) => {
    if (!rawText) return null;

    const text = normalizeSummaryText(rawText);
    const lines = text.split("\n");

    const elements: React.ReactNode[] = [];
    let listBuffer: string[] = [];
    let listType: "ul" | "ol" | null = null;
    let keyCounter = 0;

    const flushList = () => {
      if (listBuffer.length === 0 || !listType) return;
      const items = [...listBuffer];
      const type = listType;
      const key = `list-${keyCounter++}`;

      if (type === "ul") {
        elements.push(
          <ul
            key={key}
            className="flex flex-col gap-1.5 pl-6 list-disc mb-4 text-[var(--text-secondary)]"
          >
            {items.map((item, i) => (
              <li
                key={i}
                className="leading-relaxed marker:text-[var(--text-muted)] pl-1"
              >
                {renderCitations(item)}
              </li>
            ))}
          </ul>,
        );
      } else {
        elements.push(
          <ol
            key={key}
            className="flex flex-col gap-1.5 pl-6 list-decimal mb-4 text-[var(--text-secondary)]"
          >
            {items.map((item, i) => (
              <li
                key={i}
                className="leading-relaxed marker:text-[var(--text-muted)] pl-1"
              >
                {renderCitations(item)}
              </li>
            ))}
          </ol>,
        );
      }

      listBuffer = [];
      listType = null;
    };

    for (const rawLine of lines) {
      const line = rawLine.trim();

      // Empty line: flush the open list
      if (!line) {
        flushList();
        continue;
      }

      // Heading: render with normal weight, non-bold
      if (line.startsWith("§H§")) {
        flushList();
        const headingContent = line.replace(/^§H§\s*/, "");
        elements.push(
          <p
            key={`h-${keyCounter++}`}
            className="text-sm font-normal text-[var(--text-primary)] mt-5 mb-2 first:mt-0"
          >
            {renderCitations(headingContent)}
          </p>,
        );
        continue;
      }

      // Bullet point
      const bulletMatch = line.match(/^[\*\-]\s+(.*)$/);
      if (bulletMatch) {
        if (listType && listType !== "ul") flushList();
        listType = "ul";
        listBuffer.push(bulletMatch[1].trim());
        continue;
      }

      // Numbered point
      const numberedMatch = line.match(/^\d+\.\s+(.*)$/);
      if (numberedMatch) {
        if (listType && listType !== "ol") flushList();
        listType = "ol";
        listBuffer.push(numberedMatch[1].trim());
        continue;
      }

      // Plain paragraph
      flushList();
      elements.push(
        <p
          key={`p-${keyCounter++}`}
          className="mb-3 leading-relaxed text-[var(--text-secondary)]"
        >
          {renderCitations(line)}
        </p>,
      );
    }

    // Flush any remaining open list
    flushList();

    return elements;
  };

  if (isRail) {
    return (
      <div className="flex h-full flex-col bg-[var(--bg-card)]">
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-[var(--text-muted)]" />
            <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
              {t("overviewPanels.runSummary.title")}
            </span>
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              title={t("overviewPanels.domainDetails.collapseSummary")}
            >
              <X size={16} />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {summary.status === "ready" && summary.text ? (
            <div className="text-sm">{renderFormattedSummary(summary.text)}</div>
          ) : summary.status === "failed" ? (
            <FallbackSummary
              fallback={summary.fallback}
              onRegenerate={handleRegenerate}
              isRegenerating={isRegenerating}
            />
          ) : (
            <div className="flex flex-col items-center justify-center gap-3 py-8 text-center">
              <RefreshCw
                size={24}
                className="animate-spin text-[var(--accent-primary)]"
              />
              <p className="text-xs text-[var(--text-muted)]">
                {t("overviewPanels.runSummary.generating")}
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Expanded view
  return (
    <div className="flex h-full flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm overflow-hidden">
      <div className="shrink-0 flex items-start justify-between border-b border-[var(--border-subtle)] px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            {t("overviewPanels.runSummary.titleFull")}
          </h3>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            {t("overviewPanels.runSummary.disclaimer")}
            {summary.generated_at &&
              t("overviewPanels.runSummary.updated", {
                time: new Date(summary.generated_at).toLocaleString(
                  i18n.language,
                ),
              })}
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
            title={t("overviewPanels.domainDetails.collapseSummary")}
          >
            <X size={16} />
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-5">
        {summary.status === "ready" && summary.text ? (
          <div className="space-y-4">
            {/* Responsive grid: 2/3 text + 1/3 sidebar on wide viewports, full-width text on narrow screens */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              {/* Left column: summary text */}
              <div className="xl:col-span-2 text-sm min-w-0">
                {renderFormattedSummary(summary.text)}
              </div>

              {/* Right column: infographics (large viewports only) */}
              <div className="hidden xl:block xl:col-span-1 space-y-4">
                <SummaryInsights documents={documents} />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-4 border-t border-[var(--border-subtle)]">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleRegenerate}
                isLoading={isRegenerating}
                leftIcon={<RefreshCw size={14} />}
              >
                {t("overviewPanels.runSummary.regenerateFull")}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCopyText}
                leftIcon={
                  isCopied ? <Check size={14} /> : <FileText size={14} />
                }
                disabled={isCopied}
              >
                {isCopied
                  ? t("overviewPanels.runSummary.copied")
                  : t("overviewPanels.runSummary.copy")}
              </Button>
            </div>
          </div>
        ) : summary.status === "failed" ? (
          <FallbackSummary
            fallback={summary.fallback}
            onRegenerate={handleRegenerate}
            isRegenerating={isRegenerating}
          />
        ) : (
          <div className="flex flex-col items-center justify-center gap-3 py-8">
            <RefreshCw
              size={32}
              className="animate-spin text-[var(--accent-primary)]"
            />
            <p className="text-sm text-[var(--text-muted)]">
              {t("overviewPanels.runSummary.generatingLong")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Fallback
// ---------------------------------------------------------------------------

const FallbackSummary: React.FC<{
  fallback: RunSummaryResponse["fallback"];
  onRegenerate: () => void;
  isRegenerating: boolean;
}> = ({ fallback, onRegenerate, isRegenerating }) => {
  const { t } = useTranslation("projects");

  if (!fallback) return null;

  return (
    <div className="space-y-4">
      <InlineAlert
        tone="warning"
        message={t("overviewPanels.runSummary.fallbackBanner")}
      />

      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-4">
        <h4 className="text-sm font-semibold text-[var(--text-primary)]">
          {fallback.title}
        </h4>
        <div className="mt-3 grid grid-cols-2 gap-4 text-xs sm:grid-cols-4">
          <div>
            <span className="text-[var(--text-muted)]">
              {t("overviewPanels.runSummary.fallbackMetrics.totalDocs")}
            </span>
            <p className="text-base font-semibold text-[var(--text-primary)]">
              {fallback.coverage.total}
            </p>
          </div>
          <div>
            <span className="text-[var(--text-muted)]">
              {t("overviewPanels.runSummary.fallbackMetrics.processed")}
            </span>
            <p className="text-base font-semibold text-[var(--color-success-text)]">
              {fallback.coverage.processed}
            </p>
          </div>
          <div>
            <span className="text-[var(--text-muted)]">
              {t("overviewPanels.runSummary.fallbackMetrics.failedQuarantine")}
            </span>
            <p className="text-base font-semibold text-[var(--color-error-text)]">
              {fallback.coverage.failed + fallback.coverage.quarantine}
            </p>
          </div>
          <div>
            <span className="text-[var(--text-muted)]">
              {t("overviewPanels.runSummary.fallbackMetrics.pendingReview")}
            </span>
            <p className="text-base font-semibold text-[var(--color-warning-text)]">
              {fallback.coverage.pending_review}
            </p>
          </div>
        </div>

        {fallback.top_findings.length > 0 && (
          <div className="mt-4">
            <h5 className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
              {t("overviewPanels.runSummary.fallbackMetrics.topFindings")}
            </h5>
            <ul className="mt-2 space-y-2">
              {fallback.top_findings.map((f, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-xs text-[var(--text-secondary)]"
                >
                  <AlertCircle
                    size={14}
                    className={`mt-0.5 shrink-0 ${
                      f.severity === "critical"
                        ? "text-[var(--color-error-text)]"
                        : "text-[var(--color-warning-text)]"
                    }`}
                  />
                  <span>
                    <span className="font-medium text-[var(--text-primary)]">
                      {f.check_name}
                    </span>
                    <span className="text-[var(--text-muted)]">
                      {" "}
                      {t(
                        "overviewPanels.runSummary.fallbackMetrics.findingsMeta",
                        {
                          count: f.count,
                          types: f.doc_types.join(", "),
                        },
                      )}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          {fallback.actions.map((action, i) => (
            <Button key={i} variant="secondary" size="sm">
              {action.label}
            </Button>
          ))}
          <Button
            variant="primary"
            size="sm"
            onClick={onRegenerate}
            isLoading={isRegenerating}
            leftIcon={<RefreshCw size={14} />}
          >
            {t("overviewPanels.runSummary.fallbackMetrics.retry")}
          </Button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------

const EXCLUDED_STATUSES_FOR_STATS = new Set<string>(["duplicate", "deleted"]);

const SummaryInsights: React.FC<{ documents?: DocumentListItem[] }> = ({
  documents,
}) => {
  const { t } = useTranslation("projects");

  // Compute document type distribution
  const docTypeStats = React.useMemo(() => {
    if (!documents || documents.length === 0) {
      return {
        items: [] as Array<{ type: string; count: number; pct: number }>,
        total: 0,
      };
    }

    // Filter out duplicate/deleted statuses
    const activeDocs = documents.filter(
      (doc) => !EXCLUDED_STATUSES_FOR_STATS.has(doc.status),
    );

    const map = new Map<string, number>();
    for (const doc of activeDocs) {
      const type =
        doc.doc_type?.trim() ||
        t("overviewPanels.runSummary.insights.unclassified");
      map.set(type, (map.get(type) ?? 0) + 1);
    }

    const total = activeDocs.length;
    const items = Array.from(map.entries())
      .map(([type, count]) => ({
        type,
        count,
        pct: total > 0 ? (count / total) * 100 : 0,
      }))
      .sort((a, b) => b.count - a.count);

    return { items, total };
  }, [documents, t]);

  if (docTypeStats.items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-transparent p-4">
        <p className="text-[11px] text-[var(--text-muted)]">
          {t("overviewPanels.runSummary.insights.noData")}
        </p>
      </div>
    );
  }

  const maxCount = Math.max(...docTypeStats.items.map((x) => x.count), 1);

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-4">
      <div className="flex items-baseline justify-between mb-3">
        <h4 className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
          {t("overviewPanels.runSummary.insights.title")}
        </h4>
        <span className="text-[11px] text-[var(--text-muted)] tabular-nums">
          {t("overviewPanels.runSummary.insights.total", {
            count: docTypeStats.total,
          })}
        </span>
      </div>

      <div className="space-y-2.5">
        {docTypeStats.items.map(({ type, count, pct }) => {
          const barWidth = (count / maxCount) * 100;
          return (
            <div key={type}>
              <div className="flex items-center justify-between text-[11px] mb-1 gap-2">
                <span
                  className="text-[var(--text-secondary)] truncate"
                  title={type}
                >
                  {type}
                </span>
                <span className="text-[var(--text-muted)] shrink-0 tabular-nums">
                  {count} · {pct.toFixed(0)}%
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                <div
                  className="h-full bg-[var(--accent-primary)] transition-all"
                  style={{ width: `${barWidth}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default RunSummaryPanel;


