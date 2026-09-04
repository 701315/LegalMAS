// =============================================================
// src/pages/tabs/overview/LaunchFormPanel.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { Deal } from "../../../types";
import type { ChecksMode } from "../OverviewTab";
import Button from "../../../components/ui/Button";
import {
  formatLangLabel,
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../../utils/languageDiscovery";

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

const SECONDARY_ACTION_BUTTON_CLASS = "w-[220px] shrink-0 justify-center";

interface LaunchFormPanelProps {
  deal: Deal;
  hasCurrentRun: boolean;
  documentsCount?: number;
  checksMode: ChecksMode;
  onChecksModeChange: (value: ChecksMode) => void;
  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;
  canStartRun: boolean;
  canUploadDocuments: boolean;
  isSubmitting: boolean;
  onOpenPlaybook: () => void;
  onOpenModelConfig?: () => void;
  onOpenUpload: () => void;
  onPrimaryLanguageChange: (value: string) => void;
}

type BannerTone = "info" | "warning" | "error" | "success";

function formatLangHint(value: string, tFn: TranslateFn): string {
  const normalized = normalizeLang(value);

  if (normalized === "RU") {
    return tFn("overviewPanels.launchForm.langHint.RU");
  }

  if (normalized === "EN") {
    return tFn("overviewPanels.launchForm.langHint.EN");
  }

  return tFn("overviewPanels.launchForm.langHint.default");
}

function getDiscoveryBanner(
  status: string | null,
  hasLanguages: boolean,
  tFn: TranslateFn,
): {
  tone: BannerTone;
  text: string;
} | null {
  if (status === "pending") {
    return {
      tone: "info",
      text: tFn("overviewPanels.launchForm.discoveryBanner.pending"),
    };
  }

  if (status === "processing") {
    return {
      tone: "info",
      text: tFn("overviewPanels.launchForm.discoveryBanner.processing"),
    };
  }

  if (status === "failed") {
    return {
      tone: "error",
      text: tFn("overviewPanels.launchForm.discoveryBanner.failed"),
    };
  }

  if (status === "partial") {
    return {
      tone: "warning",
      text: tFn("overviewPanels.launchForm.discoveryBanner.partial"),
    };
  }

  if (status === "completed" && hasLanguages) {
    return {
      tone: "success",
      text: tFn("overviewPanels.launchForm.discoveryBanner.completed"),
    };
  }

  return null;
}

function getBannerClassName(tone: BannerTone): string {
  if (tone === "error") {
    return "border border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]";
  }

  if (tone === "warning") {
    return "border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]";
  }

  if (tone === "success") {
    return "border border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]";
  }

  return "border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";
}

function getPrimaryLanguageHelperText(
  params: {
    isDiscoveryInProgress: boolean;
    discoveryStatus: string | null;
    hasLanguages: boolean;
    primaryLanguageSelected: boolean;
  },
  tFn: TranslateFn,
): string {
  const {
    isDiscoveryInProgress,
    discoveryStatus,
    hasLanguages,
    primaryLanguageSelected,
  } = params;

  if (isDiscoveryInProgress) {
    return tFn("overviewPanels.launchForm.primaryLangHelper.inProgress");
  }

  if (!hasLanguages && discoveryStatus === "failed") {
    return tFn("overviewPanels.launchForm.primaryLangHelper.failed");
  }

  if (!hasLanguages && discoveryStatus === "partial") {
    return tFn("overviewPanels.launchForm.primaryLangHelper.partial");
  }

  if (!hasLanguages) {
    return tFn("overviewPanels.launchForm.primaryLangHelper.notDetermined");
  }

  if (!primaryLanguageSelected) {
    return tFn("overviewPanels.launchForm.primaryLangHelper.notSelected");
  }

  return tFn("overviewPanels.launchForm.primaryLangHelper.selected");
}

function getChecksModeHelperText(
  params: {
    documentsCountLoaded: boolean;
    hasDocuments: boolean;
    hasPlaybook: boolean;
    isDiscoveryInProgress: boolean;
    primaryLanguageSelected: boolean;
  },
  tFn: TranslateFn,
): string {
  const {
    documentsCountLoaded,
    hasDocuments,
    hasPlaybook,
    isDiscoveryInProgress,
    primaryLanguageSelected,
  } = params;

  if (!documentsCountLoaded) {
    return tFn("overviewPanels.launchForm.checksModeHelper.loadingData");
  }

  if (!hasDocuments) {
    return tFn("overviewPanels.launchForm.checksModeHelper.noDocs");
  }

  if (!hasPlaybook) {
    return tFn("overviewPanels.launchForm.checksModeHelper.noPlaybook");
  }

  if (isDiscoveryInProgress) {
    return tFn("overviewPanels.launchForm.checksModeHelper.inProgress");
  }

  if (!primaryLanguageSelected) {
    return tFn("overviewPanels.launchForm.checksModeHelper.noPrimaryLang");
  }

  return tFn("overviewPanels.launchForm.checksModeHelper.ready");
}

const LaunchFormPanel: React.FC<LaunchFormPanelProps> = ({
  deal,
  hasCurrentRun,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canUploadDocuments,
  isSubmitting,
  onOpenPlaybook,
  onOpenModelConfig,
  onOpenUpload,
  onPrimaryLanguageChange,
}) => {
  const { t } = useTranslation("projects");

  const normalizedDocumentLanguages = React.useMemo(
    () =>
      Array.from(
        new Set(
          (deal.languages ?? [])
            .map((lang) => normalizeLang(lang))
            .filter(Boolean),
        ),
      ),
    [deal.languages],
  );

  const selectedPrimaryLanguage = normalizeLang(deal.primary_language);

  const [isLanguageOpen, setIsLanguageOpen] = React.useState(false);
  const [isChecksModeOpen, setIsChecksModeOpen] = React.useState(false);

  const discoveryStatus = normalizeDiscoveryStatus(
    deal.language_discovery_status,
  );

  const documentsCountLoaded = typeof documentsCount === "number";
  const hasDocuments = documentsCountLoaded ? documentsCount > 0 : false;
  const hasPlaybook = !!deal.playbook_version_id;
  const hasLanguages = normalizedDocumentLanguages.length > 0;
  const primaryLanguageSelected = !!selectedPrimaryLanguage;
  const isDiscoveryInProgress =
    discoveryStatus === "pending" || discoveryStatus === "processing";

  const canSelectPrimaryLanguage =
    hasLanguages &&
    !isSubmitting &&
    !isDiscoveryInProgress;

  const canSelectChecksMode =
    documentsCountLoaded &&
    hasDocuments &&
    hasPlaybook &&
    !isSubmitting &&
    !isDiscoveryInProgress &&
    primaryLanguageSelected;

  const discoveryBanner = React.useMemo(
    () => getDiscoveryBanner(discoveryStatus, hasLanguages, t),
    [discoveryStatus, hasLanguages, t],
  );

  const autoDetectedLanguagesText = React.useMemo(
    () =>
      normalizedDocumentLanguages
        .map((lang) => formatLangLabel(lang))
        .join(", "),
    [normalizedDocumentLanguages],
  );

  const primaryLanguageHelperText = React.useMemo(
    () =>
      getPrimaryLanguageHelperText(
        {
          isDiscoveryInProgress,
          discoveryStatus,
          hasLanguages,
          primaryLanguageSelected,
        },
        t,
      ),
    [
      isDiscoveryInProgress,
      discoveryStatus,
      hasLanguages,
      primaryLanguageSelected,
      t,
    ],
  );

  const checksModeHelperText = React.useMemo(
    () =>
      getChecksModeHelperText(
        {
          documentsCountLoaded,
          hasDocuments,
          hasPlaybook,
          isDiscoveryInProgress,
          primaryLanguageSelected,
        },
        t,
      ),
    [
      documentsCountLoaded,
      hasDocuments,
      hasPlaybook,
      isDiscoveryInProgress,
      primaryLanguageSelected,
      t,
    ],
  );

  const handleLanguageSelect = React.useCallback(
    (lang: string) => {
      const normalized = normalizeLang(lang);

      if (!normalized || isSubmitting || !canSelectPrimaryLanguage) {
        return;
      }

      if (selectedPrimaryLanguage === normalized) {
        return;
      }

      onPrimaryLanguageChange(normalized);
    },
    [
      canSelectPrimaryLanguage,
      isSubmitting,
      onPrimaryLanguageChange,
      selectedPrimaryLanguage,
    ],
  );

  const formTitle = hasCurrentRun
    ? t("overviewPanels.launchForm.relaunchTitle")
    : t("overviewPanels.launchForm.launchTitle");
  const formDescription = hasCurrentRun
    ? t("overviewPanels.launchForm.relaunchDesc")
    : t("overviewPanels.launchForm.launchDesc");

  const checksModeOptions = React.useMemo(
    () => [
      {
        value: "global_and_doc_type" as const,
        title: t("overviewPanels.launchForm.checksModeOptions.global_and_doc_type.title"),
        hint: t("overviewPanels.launchForm.checksModeOptions.global_and_doc_type.hint"),
      },
      {
        value: "global_only" as const,
        title: t("overviewPanels.launchForm.checksModeOptions.global_only.title"),
        hint: t("overviewPanels.launchForm.checksModeOptions.global_only.hint"),
      },
      {
        value: "doc_type_only" as const,
        title: t("overviewPanels.launchForm.checksModeOptions.doc_type_only.title"),
        hint: t("overviewPanels.launchForm.checksModeOptions.doc_type_only.hint"),
      },
    ],
    [t],
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--bg-card)]">
      <div className="border-b border-[var(--border-subtle)] px-5 py-4">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">
          {formTitle}
        </h3>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {formDescription}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-3">
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("overviewPanels.launchForm.documentsTitle")}
                </h4>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  {documentsCountLoaded
                    ? t("overviewPanels.launchForm.documentsLoaded", { count: documentsCount })
                    : t("overviewPanels.launchForm.loadingData")}
                </p>
              </div>

              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenUpload}
                disabled={!canUploadDocuments}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                {t("overviewPanels.launchForm.uploadNewDocs")}
              </Button>
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("overviewPanels.launchForm.playbookTitle")}
                </h4>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {t("overviewPanels.launchForm.playbookSub")}
                </p>
              </div>

              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenPlaybook}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                {t("overviewPanels.launchForm.selectPlaybook")}
              </Button>
            </div>

            <p className="mt-3 text-xs leading-5">
              {hasPlaybook ? (
                <span className="text-[var(--text-secondary)]">
                  {t("overviewPanels.launchForm.playbookSelected")}
                </span>
              ) : (
                <span className="text-[var(--color-error-text)]">
                  {t("overviewPanels.launchForm.playbookNotSelected")}
                </span>
              )}
            </p>
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("overviewPanels.launchForm.modelProfileTitle")}
                </h4>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {t("overviewPanels.launchForm.modelProfileSub")}
                </p>
              </div>

              {onOpenModelConfig ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onOpenModelConfig}
                  className={SECONDARY_ACTION_BUTTON_CLASS}
                >
                  {t("overviewPanels.launchForm.configureProfile")}
                </Button>
              ) : null}
            </div>

            <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
              {deal.model_config_name
                ? t("overviewPanels.launchForm.profileUsed", { name: deal.model_config_name })
                : t("overviewPanels.launchForm.defaultProfileUsed")}
            </p>
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)]">
            <button
              type="button"
              onClick={() => setIsLanguageOpen((prev) => !prev)}
              className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
            >
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("overviewPanels.launchForm.primaryLangTitle")}
                </h4>
                {!isLanguageOpen && (
                  <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
                    {selectedPrimaryLanguage
                      ? formatLangLabel(selectedPrimaryLanguage)
                      : t("overviewPanels.launchForm.notSelected")}
                  </p>
                )}
              </div>
              <span
                className={[
                  "shrink-0 text-[var(--text-muted)] transition-transform duration-200",
                  isLanguageOpen ? "rotate-180" : "",
                ].join(" ")}
              >
                ▾
              </span>
            </button>

            {isLanguageOpen && (
              <>
                <div className="mx-4 border-t border-[var(--border-subtle)]" />
                <div className="p-4">
                  <p className="text-xs text-[var(--text-secondary)]">
                    {t("overviewPanels.launchForm.langDiscoveryIntro")}
                  </p>

                  {discoveryBanner ? (
                    <p
                      className={`mt-3 rounded-xl px-3 py-2 text-[11px] leading-5 ${getBannerClassName(
                        discoveryBanner.tone,
                      )}`}
                    >
                      {discoveryBanner.text}
                    </p>
                  ) : null}

                  <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
                    {primaryLanguageHelperText}
                  </p>

                  {hasLanguages ? (
                    <>
                      <div className="mt-3 space-y-2">
                        {normalizedDocumentLanguages.map((lang) => {
                          const checked = selectedPrimaryLanguage === lang;
                          const disabled = !canSelectPrimaryLanguage;

                          return (
                            <label
                              key={lang}
                              className={`flex items-start gap-3 rounded-xl border px-3 py-3 transition ${
                                checked
                                  ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                                  : "border-[var(--border-subtle)] bg-[var(--bg-card)]"
                              } ${
                                disabled
                                  ? "cursor-not-allowed opacity-70"
                                  : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]"
                              }`}
                              aria-disabled={disabled}
                            >
                              <input
                                type="radio"
                                name="primary_language"
                                className="mt-[2px]"
                                value={lang}
                                checked={checked}
                                onChange={() => handleLanguageSelect(lang)}
                                disabled={disabled}
                              />

                              <span>
                                <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                                  {formatLangLabel(lang)}
                                </span>
                                <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                                  {formatLangHint(lang, t)}
                                </span>
                              </span>
                            </label>
                          );
                        })}
                      </div>

                      {!primaryLanguageSelected && !isDiscoveryInProgress && (
                        <p className="mt-3 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2 text-[11px] leading-5 text-[var(--color-warning-text)]">
                          {t("overviewPanels.launchForm.selectPrimaryLangWarning")}
                        </p>
                      )}

                      <p className="mt-2 text-xs text-[var(--text-secondary)]">
                        {t("overviewPanels.launchForm.autoDetectedLangs", { langs: autoDetectedLanguagesText })}
                      </p>
                    </>
                  ) : (
                    <p className="mt-3 text-xs text-[var(--text-secondary)]">
                      {discoveryStatus === "failed"
                        ? t("overviewPanels.launchForm.langDiscoveryFailed")
                        : t("overviewPanels.launchForm.langDiscoveryNotReady")}
                    </p>
                  )}
                </div>
              </>
            )}
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)]">
            <button
              type="button"
              onClick={() => setIsChecksModeOpen((prev) => !prev)}
              className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
            >
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("overviewPanels.launchForm.checksModeTitle")}
                </h4>
                {!isChecksModeOpen && (
                  <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
                    {checksModeOptions.find((o) => o.value === checksMode)?.title ??
                      t("overviewPanels.launchForm.notSelected")}
                  </p>
                )}
              </div>
              <span
                className={[
                  "shrink-0 text-[var(--text-muted)] transition-transform duration-200",
                  isChecksModeOpen ? "rotate-180" : "",
                ].join(" ")}
              >
                ▾
              </span>
            </button>

            {isChecksModeOpen && (
              <>
                <div className="mx-4 border-t border-[var(--border-subtle)]" />
                <div className="p-4">
                  <p className="text-xs leading-5 text-[var(--text-secondary)]">
                    {checksModeHelperText}
                  </p>

                  <div className="mt-3 space-y-2">
                    {checksModeOptions.map(({ value, title, hint }) => {
                      const checked = checksMode === value;
                      const disabled = !canSelectChecksMode;

                      return (
                        <label
                          key={value}
                          className={`flex items-start gap-3 rounded-xl border px-3 py-3 transition ${
                            checked
                              ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                              : "border-[var(--border-subtle)] bg-[var(--bg-card)]"
                          } ${
                            disabled
                              ? "cursor-not-allowed opacity-70"
                              : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]"
                          }`}
                          aria-disabled={disabled}
                        >
                          <input
                            type="radio"
                            className="mt-[2px]"
                            value={value}
                            checked={checked}
                            onChange={() => onChecksModeChange(value)}
                            disabled={disabled}
                          />

                          <span>
                            <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                              {title}
                            </span>
                            <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                              {hint}
                            </span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </section>

          {deal.has_pending_manual_reclassifications ? (
            <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("overviewPanels.launchForm.reclassifySection")}
              </h4>

              <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  className="mt-[2px]"
                  checked={forceReclassify}
                  onChange={(e) => onForceReclassifyChange(e.target.checked)}
                  disabled={isSubmitting}
                />

                <span>
                  <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                    {t("overviewPanels.launchForm.reclassifyCheckbox")}
                  </span>
                  <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                    {t("overviewPanels.launchForm.reclassifyHint")}
                  </span>
                </span>
              </label>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default LaunchFormPanel;


