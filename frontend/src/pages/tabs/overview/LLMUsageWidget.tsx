// =============================================================
// src/pages/tabs/overview/LLMUsageWidget.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type {
  LLMUsageSummary,
  LLMStageUsage,
  LLMDocumentUsage,
} from "../../../api/deals";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

// ---------------------------------------------------------------------------
// DocumentRow Fallback
// ---------------------------------------------------------------------------

function formatFallbackDocumentLabel(documentId: string): string {
  return `${documentId.slice(0, 8)}…`;
}

// ---------------------------------------------------------------------------
// StageRow
// ---------------------------------------------------------------------------

const StageRow: React.FC<{ stage: LLMStageUsage }> = ({ stage }) => {
  const { t } = useTranslation("projects");
  const label = t(`overviewPanels.llmWidget.stages.${stage.stage}`, { defaultValue: stage.stage });

  return (
    <div className="flex items-start justify-between gap-2 py-1.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          {label}
        </p>
        <p className="text-[10px] text-[var(--text-muted)]">
          {t("overviewPanels.llmWidget.callsShort", { count: stage.calls })}
          {stage.parse_failures > 0 && (
            <span
              className="ml-1 cursor-help text-[var(--color-warning-text)]"
              title={t("overviewPanels.llmWidget.parseErrorTooltip")}
            >
              · {t("overviewPanels.llmWidget.parseFailures", { count: stage.parse_failures })}
            </span>
          )}
        </p>
      </div>
      <span className="shrink-0 text-[12px] font-semibold tabular-nums text-[var(--text-primary)]">
        {formatTokens(stage.total_tokens)}
      </span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// DocumentRow
// ---------------------------------------------------------------------------

const DocumentRow: React.FC<{
  doc: LLMDocumentUsage;
  filename: string | null;
}> = ({ doc, filename }) => {
  const { t } = useTranslation("projects");
  const displayName = filename ?? formatFallbackDocumentLabel(doc.document_id);

  return (
    <div className="flex items-start justify-between gap-2 py-1.5">
      <div className="min-w-0 flex-1">
        <p
          className="truncate text-[11px] text-[var(--text-secondary)]"
          title={filename ? `${filename}\n${doc.document_id}` : doc.document_id}
        >
          {displayName}
        </p>
        <p className="text-[10px] text-[var(--text-muted)]">
          {t("overviewPanels.llmWidget.callsShort", { count: doc.calls })}
          {doc.parse_failures > 0 && (
            <span
              className="ml-1 cursor-help text-[var(--color-warning-text)]"
              title={t("overviewPanels.llmWidget.parseErrorTooltip")}
            >
              · {t("overviewPanels.llmWidget.parseFailures", { count: doc.parse_failures })}
            </span>
          )}
        </p>
      </div>
      <span className="shrink-0 text-[12px] font-semibold tabular-nums text-[var(--text-primary)]">
        {formatTokens(doc.total_tokens)}
      </span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Skeleton / Empty
// ---------------------------------------------------------------------------

export const LLMUsageWidgetSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-2">
    <div className="h-3 w-20 rounded-lg bg-[var(--bg-elevated-soft)]" />
    <div className="h-7 w-28 rounded-lg bg-[var(--bg-elevated-soft)]" />
    <div className="space-y-1.5 pt-1">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-8 rounded-lg bg-[var(--bg-elevated-soft)]" />
      ))}
    </div>
  </div>
);

export const LLMUsageWidgetEmpty: React.FC = () => {
  const { t } = useTranslation("projects");
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-4 text-center">
      <p className="text-[11px] text-[var(--text-muted)]">
        {t("overviewPanels.llmWidget.emptyTitle")}
      </p>
      <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
        {t("overviewPanels.llmWidget.emptySub")}
      </p>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

interface LLMUsageWidgetProps {
  data: LLMUsageSummary | undefined;
  isLoading: boolean;
  isError: boolean;
  documentNames?: Record<string, string>;
}

export const LLMUsageWidget: React.FC<LLMUsageWidgetProps> = ({
  data,
  isLoading,
  isError,
  documentNames,
}) => {
  const { t } = useTranslation("projects");

  if (isLoading) return <LLMUsageWidgetSkeleton />;

  if (isError || !data) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          {t("overviewPanels.llmWidget.loadError")}
        </p>
      </div>
    );
  }

  if (data.total_calls === 0) return <LLMUsageWidgetEmpty />;

  const model = data.by_stage[0]?.model;

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          {t("overviewPanels.llmWidget.title")}
        </p>
        <p className="mt-1 text-xl font-semibold tracking-tight tabular-nums text-[var(--text-primary)]">
          {formatTokens(data.total_tokens)}
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
          {t("overviewPanels.llmWidget.calls", { count: data.total_calls })}
        </p>
        {model && (
          <p className="mt-1 truncate text-[10px] text-[var(--text-muted)]">
            {t("overviewPanels.llmWidget.model", { model })}
          </p>
        )}
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2">
        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          {t("overviewPanels.llmWidget.byStage")}
        </p>
        <div className="divide-y divide-[var(--border-subtle)]">
          {data.by_stage.map((stage) => (
            <StageRow
              key={`${stage.stage}-${stage.model}`}
              stage={stage}
            />
          ))}
        </div>
      </div>

      {data.by_document.length > 0 && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2">
          <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
            {t("overviewPanels.llmWidget.byDocument")}
          </p>
          <div className="divide-y divide-[var(--border-subtle)]">
            {data.by_document.map((doc) => (
              <DocumentRow
                key={doc.document_id}
                doc={doc}
                filename={documentNames?.[doc.document_id] ?? null}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default LLMUsageWidget;


