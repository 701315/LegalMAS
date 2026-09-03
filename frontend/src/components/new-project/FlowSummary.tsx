// =============================================================
// src/components/new-project/FlowSummary.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Check, Circle } from "lucide-react";

export interface FlowSummaryData {
  projectName: string | null;
  documentsCount: number;
  playbookLabel: string | null;
  modelConfigLabel: string | null;
  primaryLanguage: string | null;
}

interface FlowSummaryProps {
  data: FlowSummaryData;
}

interface SummaryRowProps {
  label: string;
  value: string | null;
  isSet: boolean;
  emptyLabel: string;
}

const SummaryRow: React.FC<SummaryRowProps> = ({ label, value, isSet, emptyLabel }) => {
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <div
        className={[
          "mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full",
          isSet
            ? "text-[var(--color-success-text)]"
            : "text-[var(--text-faint)]",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-hidden="true"
      >
        {isSet ? (
          <Check className="h-3 w-3" strokeWidth={2.5} />
        ) : (
          <Circle className="h-2 w-2 fill-current" strokeWidth={0} />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
          {label}
        </p>
        <p
          className={[
            "mt-0.5 truncate text-[12px]",
            isSet
              ? "text-[var(--text-primary)] font-medium"
              : "text-[var(--text-faint)] italic",
          ]
            .filter(Boolean)
            .join(" ")}
          title={value ?? undefined}
        >
          {value ?? emptyLabel}
        </p>
      </div>
    </div>
  );
};

const FlowSummary: React.FC<FlowSummaryProps> = ({ data }) => {
  const { t } = useTranslation("projects");
  const notSetLabel = t("flowSummary.notSet");

  const documentsValue =
    data.documentsCount > 0
      ? t("flowSummary.documentsCount", { count: data.documentsCount })
      : null;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          {t("flowSummary.title")}
        </h3>
      </div>

      <div className="divide-y divide-[var(--border-subtle)]">
        <SummaryRow
          label={t("flowSummary.labels.name")}
          value={data.projectName}
          isSet={!!data.projectName}
          emptyLabel={notSetLabel}
        />
        <SummaryRow
          label={t("flowSummary.labels.documents")}
          value={documentsValue}
          isSet={data.documentsCount > 0}
          emptyLabel={notSetLabel}
        />
        <SummaryRow
          label={t("flowSummary.labels.playbook")}
          value={data.playbookLabel}
          isSet={!!data.playbookLabel}
          emptyLabel={notSetLabel}
        />
        <SummaryRow
          label={t("flowSummary.labels.modelProfile")}
          value={data.modelConfigLabel}
          isSet={!!data.modelConfigLabel}
          emptyLabel={notSetLabel}
        />
        <SummaryRow
          label={t("flowSummary.labels.primaryLanguage")}
          value={data.primaryLanguage}
          isSet={!!data.primaryLanguage}
          emptyLabel={notSetLabel}
        />
      </div>
    </section>
  );
};

export default FlowSummary;


