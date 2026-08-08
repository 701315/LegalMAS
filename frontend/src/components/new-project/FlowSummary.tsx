// =============================================================
// src/components/new-project/FlowSummary.tsx
//
// Компактная сводка проекта для правой колонки.
//
// Показывает 6 параметров с текущими значениями:
//   - Название проекта
//   - Ответственный
//   - Документы
//   - Playbook
//   - Профиль модели
//   - Основной язык
//
// Каждый параметр — либо значение, либо placeholder "Не задано".
// Индикатор состояния: ✓ (заполнено) / • (пусто).
// =============================================================

import React from "react";
import { Check, Circle } from "lucide-react";

export interface FlowSummaryData {
  projectName: string | null;
  responsibleUser: string | null;
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
}

const SummaryRow: React.FC<SummaryRowProps> = ({ label, value, isSet }) => {
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
          {value ?? "Не задано"}
        </p>
      </div>
    </div>
  );
};

const FlowSummary: React.FC<FlowSummaryProps> = ({ data }) => {
  const documentsValue =
    data.documentsCount > 0
      ? `${data.documentsCount} ${
          data.documentsCount === 1
            ? "документ"
            : data.documentsCount < 5
              ? "документа"
              : "документов"
        }`
      : null;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Сводка проекта
        </h3>
      </div>

      <div className="divide-y divide-[var(--border-subtle)]">
        <SummaryRow
          label="Название"
          value={data.projectName}
          isSet={!!data.projectName}
        />

        <SummaryRow
          label="Ответственный"
          value={data.responsibleUser}
          isSet={!!data.responsibleUser}
        />

        <SummaryRow
          label="Документы"
          value={documentsValue}
          isSet={data.documentsCount > 0}
        />

        <SummaryRow
          label="Playbook"
          value={data.playbookLabel}
          isSet={!!data.playbookLabel}
        />

        <SummaryRow
          label="Профиль модели"
          value={data.modelConfigLabel}
          isSet={!!data.modelConfigLabel}
        />

        <SummaryRow
          label="Основной язык"
          value={data.primaryLanguage}
          isSet={!!data.primaryLanguage}
        />
      </div>
    </section>
  );
};

export default FlowSummary;


