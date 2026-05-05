import React from "react";
import type { Deal } from "../../../types";
import type { ChecksMode } from "../OverviewTab";

interface PipelinePreviewPanelProps {
  deal: Deal;
  documentsCount?: number;
  checksMode: ChecksMode;
  forceReclassify: boolean;
}

type StepStatus = "done" | "active" | "pending";

interface PipelineStep {
  number: number;
  title: string;
  description: string;
  status: StepStatus;
}

const PipelineStepCard: React.FC<{
  stepNumber: number;
  title: string;
  description: string;
  status: StepStatus;
  isLast?: boolean;
}> = ({ stepNumber, title, description, status, isLast = false }) => {
  const badgeClass =
    status === "done"
      ? "bg-emerald-100 text-emerald-700"
      : status === "active"
        ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
        : "bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]";

  const dotClass =
    status === "done"
      ? "bg-emerald-500"
      : status === "active"
        ? "bg-[var(--accent-primary)]"
        : "bg-[var(--border)]";

  return (
    <div className="relative pl-10">
      {!isLast && (
        <div className="absolute left-[15px] top-8 bottom-[-16px] w-px bg-[var(--border-soft)]" />
      )}

      <div
        className={`absolute left-0 top-1 flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border-soft)] ${dotClass} text-xs font-semibold text-white`}
      >
        {stepNumber}
      </div>

      <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-card)] px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            {title}
          </h4>

          <span
            className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] ${badgeClass}`}
          >
            {status === "done"
              ? "Готово"
              : status === "active"
                ? "Активный этап"
                : "Ожидание"}
          </span>
        </div>

        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          {description}
        </p>
      </div>
    </div>
  );
};

const PipelinePreviewPanel: React.FC<PipelinePreviewPanelProps> = ({
  deal,
  documentsCount,
  checksMode,
  forceReclassify,
}) => {
  const hasPlaybook = !!deal.playbook_version_id;
  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const selectedPrimaryLanguage = deal.primary_language ?? "";
  const hasLanguageIssue =
    hasMultipleDocumentLanguages && !selectedPrimaryLanguage;

  const launchReadiness: "ready" | "attention" =
    hasPlaybook && !hasLanguageIssue ? "ready" : "attention";

  const checksModeLabel =
    checksMode === "global_and_doc_type"
      ? "Playbook + типы документов"
      : checksMode === "global_only"
        ? "Только Playbook"
        : "Только типы документов";

  const pipelineSteps: PipelineStep[] = [
    {
      number: 1,
      title: "Фиксация входного набора",
      description:
        typeof documentsCount === "number"
          ? `В запуск попадут ${documentsCount} документ(ов) из текущего состава проекта.`
          : "Сначала фиксируется актуальный состав документов проекта.",
      status: "done",
    },
    {
      number: 2,
      title: "Определение правил проверки",
      description: `Для запуска выбран режим: ${checksModeLabel}.`,
      status: "active",
    },
    {
      number: 3,
      title: "Языковая и модельная настройка",
      description: hasMultipleDocumentLanguages
        ? selectedPrimaryLanguage
          ? `Основной язык анализа: ${selectedPrimaryLanguage}.`
          : "Перед запуском требуется выбрать основной язык анализа."
        : "Дополнительный выбор языка не требуется.",
      status: hasLanguageIssue ? "active" : "done",
    },
    {
      number: 4,
      title: forceReclassify
        ? "Повторная классификация и запуск пайплайна"
        : "Запуск пайплайна анализа",
      description: forceReclassify
        ? "Будет выполнена повторная классификация документов, затем полный анализ по выбранным правилам."
        : "Будут выполнены классификация, проверки по правилам и обновление результатов проекта.",
      status: "pending",
    },
  ];

  return (
    <div className="min-w-0 text-[var(--text-primary)]">
      <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-card)] px-4 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Launch readiness
            </p>

            <h4 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {launchReadiness === "ready"
                ? "Конфигурация готова к запуску"
                : "Перед запуском нужно завершить обязательные настройки"}
            </h4>

            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              Визуализация сценария анализа на основе текущих параметров.
            </p>
          </div>

          <span
            className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] ${
              launchReadiness === "ready"
                ? "bg-emerald-100 text-emerald-700"
                : "bg-amber-100 text-amber-800"
            }`}
          >
            {launchReadiness === "ready" ? "Ready" : "Attention"}
          </span>
        </div>

        <div className="mt-4 space-y-4">
          {pipelineSteps.map((step, index) => (
            <PipelineStepCard
              key={step.number}
              stepNumber={step.number}
              title={step.title}
              description={step.description}
              status={step.status}
              isLast={index === pipelineSteps.length - 1}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default PipelinePreviewPanel;




