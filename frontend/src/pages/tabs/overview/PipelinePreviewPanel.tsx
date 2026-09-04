// =============================================================
// src/pages/tabs/overview/PipelinePreviewPanel.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("projects");

  const checksModeLabel = t(
    `overviewPanels.pipelinePreview.checksMode.${checksMode}`,
  );

  const primaryLanguage = normalizeLang(deal.primary_language);
  const primaryLanguageLabel = primaryLanguage
    ? formatLangLabel(primaryLanguage)
    : t("overviewPanels.pipelinePreview.primaryLangNotSelected");

  const documentsLabel =
    typeof documentsCount === "number"
      ? t("overviewPanels.pipelinePreview.documentsCount", {
          count: documentsCount,
        })
      : t("overviewPanels.pipelinePreview.documentsCurrent");

  const playbookLabel = deal.playbook_version_id
    ? t("overviewPanels.pipelinePreview.playbookSelected")
    : t("overviewPanels.pipelinePreview.playbookNotSelected");

  const modelProfileLabel =
    deal.model_config_name ||
    t("overviewPanels.pipelinePreview.defaultModelProfile");

  const panelLabel = hasCurrentRun
    ? t("overviewPanels.pipelinePreview.categoryRelaunch")
    : t("overviewPanels.pipelinePreview.categoryLaunch");
  const panelTitle = hasCurrentRun
    ? t("overviewPanels.pipelinePreview.titleRelaunch")
    : t("overviewPanels.pipelinePreview.titleLaunch");
  const panelDescription = hasCurrentRun
    ? t("overviewPanels.pipelinePreview.descRelaunch")
    : t("overviewPanels.pipelinePreview.descLaunch");

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
              {t("overviewPanels.pipelinePreview.relaunchHint")}
            </p>
          )}
        </div>

        <div className="mt-4 space-y-4">
          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-4">
            <h5 className="text-sm font-semibold text-[var(--text-primary)]">
              {t("overviewPanels.pipelinePreview.whatGoesIn")}
            </h5>

            <dl className="mt-4 space-y-3">
              <SummaryRow
                label={t("overviewPanels.pipelinePreview.labels.documents")}
                value={documentsLabel}
              />
              <SummaryRow
                label={t("overviewPanels.pipelinePreview.labels.playbook")}
                value={playbookLabel}
              />
              <SummaryRow
                label={t("overviewPanels.pipelinePreview.labels.modelProfile")}
                value={modelProfileLabel}
              />
              <SummaryRow
                label={t(
                  "overviewPanels.pipelinePreview.labels.primaryLanguage",
                )}
                value={primaryLanguageLabel}
              />
              <SummaryRow
                label={t("overviewPanels.pipelinePreview.labels.checksMode")}
                value={checksModeLabel}
              />
            </dl>
          </section>

          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-4">
            <h5 className="text-sm font-semibold text-[var(--text-primary)]">
              {t("overviewPanels.pipelinePreview.whatHappens")}
            </h5>

            <ul className="mt-4 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
              <li className="flex items-start gap-2">
                <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                  •
                </span>
                <span>{t("overviewPanels.pipelinePreview.bullets.docsInScope")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                  •
                </span>
                <span>
                  {t("overviewPanels.pipelinePreview.bullets.settingsApplied")}
                </span>
              </li>
              {forceReclassify && (
                <li className="flex items-start gap-2">
                  <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                    •
                  </span>
                  <span className="font-medium text-[var(--text-primary)]">
                    {t(
                      "overviewPanels.pipelinePreview.bullets.forceReclassify",
                    )}
                  </span>
                </li>
              )}
              <li className="flex items-start gap-2">
                <span className="mt-[3px] shrink-0 text-[var(--accent-primary)]">
                  •
                </span>
                <span>
                  {hasCurrentRun
                    ? t("overviewPanels.pipelinePreview.bullets.resultsUpdate")
                    : t("overviewPanels.pipelinePreview.bullets.resultsFirst")}
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


