// =============================================================
// src/pages/tabs/overview/AnalysisActionsPanel.tsx
// Panel containing analysis launch/relaunch actions on Overview tab.
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { Deal } from "../../../types";
import Button from "../../../components/ui/Button";
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../../utils/languageDiscovery";

interface AnalysisActionsPanelProps {
  deal: Deal;
  hasCurrentRun: boolean;
  canStartRun: boolean;
  onOpenRunPanel: () => void;
  showReclassBanner: boolean;
}

const AnalysisActionsPanel: React.FC<AnalysisActionsPanelProps> = ({
  deal,
  hasCurrentRun,
  canStartRun,
  onOpenRunPanel,
  showReclassBanner,
}) => {
  const { t } = useTranslation("projects");
  const hasPlaybook = !!deal.playbook_version_id;
  const documentLanguages = Array.from(
    new Set(
      (deal.languages ?? [])
        .map((lang) => normalizeLang(lang))
        .filter(Boolean),
    ),
  );

  const discoveryStatus = normalizeDiscoveryStatus(
    deal.language_discovery_status,
  );
  const primaryLanguage = normalizeLang(deal.primary_language);
  const primaryLanguageSelected = !!primaryLanguage;

  const readinessText = canStartRun
    ? hasCurrentRun
      ? t("overviewPanels.actionsPanel.readiness.canRelaunch")
      : t("overviewPanels.actionsPanel.readiness.canLaunch")
    : !hasPlaybook
      ? t("overviewPanels.actionsPanel.readiness.noPlaybook")
      : !primaryLanguageSelected
        ? t("overviewPanels.actionsPanel.readiness.noPrimaryLang")
        : documentLanguages.length === 0 && discoveryStatus === "processing"
          ? t("overviewPanels.actionsPanel.readiness.langDiscoveryProcessing")
          : hasCurrentRun
            ? t("overviewPanels.actionsPanel.readiness.checkSettingsRelaunch")
            : t("overviewPanels.actionsPanel.readiness.checkSettingsLaunch");

  const panelTitle = hasCurrentRun
    ? t("overviewPanels.actionsPanel.relaunchTitle")
    : t("overviewPanels.actionsPanel.launchTitle");
  const panelDescription = hasCurrentRun
    ? t("overviewPanels.actionsPanel.relaunchDesc")
    : t("overviewPanels.actionsPanel.launchDesc");

  const buttonLabel = hasCurrentRun
    ? t("overviewPanels.actionsPanel.configureRelaunch")
    : t("overviewPanels.actionsPanel.configureLaunch");

  return (
    <aside
      className="self-start rounded-2xl bg-[var(--bg-card)] xl:sticky xl:top-0"
      style={{
        border: "1px solid var(--border)",
        boxShadow:
          "inset 0 0 0 1px var(--accent-primary), var(--shadow-sm)",
      }}
    >
      <div className="flex flex-col gap-4 p-5">
        {/* Header */}
        <div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            {t("overviewPanels.actionsPanel.title")}
          </h2>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {panelTitle}
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-muted)]">
            {panelDescription}
          </p>
        </div>

        {/* When is relaunch needed block */}
        {hasCurrentRun && (
          <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
            <p className="text-xs font-semibold text-[var(--text-secondary)]">
              {t("overviewPanels.actionsPanel.whenNeededTitle")}
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-[var(--text-muted)]">
              <li>{t("overviewPanels.actionsPanel.whenNeeded.newDocs")}</li>
              <li>{t("overviewPanels.actionsPanel.whenNeeded.newPlaybook")}</li>
              <li>{t("overviewPanels.actionsPanel.whenNeeded.afterReclass")}</li>
            </ul>
          </div>
        )}

        {/* Manual reclassification notice banner */}
        {showReclassBanner && (
          <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3">
            <p className="text-xs font-semibold text-[var(--color-warning-text)]">
              {t("overviewTab.warningReclassifications.title")}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--color-warning-text)]">
              {t("overviewTab.warningReclassifications.description")}
            </p>
          </div>
        )}

        {/* Readiness checklist block */}
        <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {hasCurrentRun
              ? t("overviewPanels.actionsPanel.readinessRelaunch")
              : t("overviewPanels.actionsPanel.readinessLaunch")}
          </p>
          <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
            {readinessText}
          </p>
        </div>

        {/* Configure button */}
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenRunPanel}
          >
            {buttonLabel}
          </Button>
        </div>
      </div>
    </aside>
  );
};

export default AnalysisActionsPanel;


