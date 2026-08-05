// =============================================================
// src/pages/tabs/overview/PipelinePreviewPanel.tsx
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import type { ChecksMode } from "../OverviewTab";
import {
  formatLangLabel,
  normalizeLang,
} from "../../../utils/languageDiscovery";

interface PipelinePreviewPanelProps {
  deal: Deal;
  hasCurrentRun: boolean;
  documentsCount?: number;
  checksMode: ChecksMode;
  forceReclassify: boolean;
}

const SummaryRow: React.FC<{
  label: string;
  value: string;
}> = ({ label, value }) => (
  <div className="flex items-start justify-between gap-4">
    <dt className="min-w-0 shrink-0 text-sm text-[var(--text-muted)]">
      {label}
    </dt>
    <dd className="text-right text-sm font-medium text-[var(--text-primary)]">
      {value}
    </dd>
  </div>
);

const PipelinePreviewPanel: React.FC<PipelinePreviewPanelProps> = ({
  deal,
  hasCurrentRun,
  documentsCount,
  checksMode,
  forceReclassify,
}) => {
  const checksModeLabel =
    checksMode === "global_and_doc_type"
      ? "Playbook + типы документов"
      : checksMode === "global_only"
        ? "Только Playbook"
        : "Только типы документов";

  const primaryLanguage = normalizeLang(deal.primary_language);
  const primaryLanguageLabel = primaryLanguage
    ? formatLangLabel(primaryLanguage)
    : "Не выбран";

  const documentsLabel =
    typeof documentsCount === "number"
      ? `${documentsCount} документ(ов) в проекте`
      : "Текущий состав проекта";

  const playbookLabel = deal.playbook_version_id
    ? "Выбранный playbook проекта"
    : "Не выбран";

  const modelProfileLabel = deal.model_config_name || "Профиль по умолчанию";

  const panelLabel = hasCurrentRun ? "Повторный анализ" : "Новый анализ";
  const panelTitle = hasCurrentRun ? "Сводка перезапуска" : "Сводка запуска";
  const panelDescription = hasCurrentRun
    ? "Что пойдёт в работу и что изменится после перезапуска."
    : "Что пойдёт в работу и что будет сформировано после запуска.";

  return (
    <div className="min-w-0 text-[var(--text-primary)]">
      <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-card)] px-4 py-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {panelLabel}
          </p>

          <h4 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {panelTitle}
          </h4>

          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {panelDescription}
          </p>

          {hasCurrentRun && (
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              Полезно, если вы добавили документы, сменили playbook или вручную
              изменили типы документов.
            </p>
          )}
        </div>

        <div className="mt-4 space-y-4">
          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-4">
            <h5 className="text-sm font-semibold text-[var(--text-primary)]">
              Что пойдёт в работу
            </h5>

            <dl className="mt-4 space-y-3">
              <SummaryRow label="Документы" value={documentsLabel} />
              <SummaryRow label="Playbook" value={playbookLabel} />
              <SummaryRow label="Профиль модели" value={modelProfileLabel} />
              <SummaryRow
                label="Основной язык"
                value={primaryLanguageLabel}
              />
              <SummaryRow
                label="Режим проверки"
                value={checksModeLabel}
              />
            </dl>
          </section>

          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-4">
            <h5 className="text-sm font-semibold text-[var(--text-primary)]">
              Что произойдёт
            </h5>

            <ul className="mt-4 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
              <li className="flex items-start gap-2">
                <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                  •
                </span>
                <span>
                  В анализ попадут документы из текущего состава проекта.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                  •
                </span>
                <span>
                  Будут применены текущие настройки проекта и выбранный режим
                  проверки.
                </span>
              </li>
              {forceReclassify && (
                <li className="flex items-start gap-2">
                  <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                    •
                  </span>
                  <span className="font-medium text-[var(--text-primary)]">
                    Документы будут переклассифицированы заново.
                  </span>
                </li>
              )}
              <li className="flex items-start gap-2">
                <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                  •
                </span>
                <span>
                  {hasCurrentRun
                    ? "Результаты проекта будут обновлены."
                    : "Будут сформированы первые результаты проекта."}
                </span>
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
};

export default PipelinePreviewPanel;


