// =============================================================
// src/components/requests/shared/RequestStructuredValuesList.tsx
// Shared UI компонент для отображения извлечённых значений (structured values).
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { StructuredValueView } from "../../../viewAdapters/requestPresentation";

interface RequestStructuredValuesListProps {
  values: StructuredValueView[];
  maxHeight?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function formatKeyLabel(key: string): string {
  return key.replace(/_/g, " ");
}

export const RequestStructuredValuesList: React.FC<
  RequestStructuredValuesListProps
> = ({ values, maxHeight = "10rem" }) => {
  const { t } = useTranslation("requests");

  if (values.length === 0) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-3">
        <p className="text-[12px] text-[var(--text-muted)]">
          {t("shared.structuredValuesList.empty")}
        </p>
      </div>
    );
  }

  return (
    <div
      className="overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-2"
      style={{ maxHeight }}
    >
      <dl className="space-y-1">
        {values.map((sv, index) => (
          <div
            key={`${sv.key}-${index}`}
            className={cn(
              "rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2.5",
              "sm:grid sm:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] sm:items-start sm:gap-3",
            )}
          >
            <dt className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[12px] font-medium capitalize text-[var(--text-secondary)]">
                  {formatKeyLabel(sv.key)}
                </span>
                {sv.format && (
                  <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em] text-[var(--text-muted)]">
                    {sv.format}
                  </span>
                )}
              </div>
            </dt>

            <dd className="mt-1 min-w-0 sm:mt-0">
              <p className="break-words text-sm font-medium leading-6 text-[var(--text-primary)] sm:text-right">
                {sv.value}
              </p>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
};

export default RequestStructuredValuesList;



