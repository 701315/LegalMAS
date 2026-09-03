// src/components/deals/RunLaunchDrawer.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import type { Deal } from "../../types/deals";
import Drawer from "../ui/Drawer";
import Button from "../ui/Button";

type ChecksMode = "global_only" | "doc_type_only" | "global_and_doc_type";

interface RunLaunchDrawerProps {
  open: boolean;
  onClose: () => void;
  deal: Deal;
  currentRunId?: string | null;
  documentsCount?: number;

  checksMode: ChecksMode;
  onChecksModeChange: (value: ChecksMode) => void;

  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;

  canStartRun: boolean;
  canUploadDocuments: boolean;
  canLaunchRun: boolean;
  isSubmitting: boolean;

  onOpenPlaybook: () => void;
  onOpenModelConfig?: () => void;
  onOpenUpload: () => void;
  onPrimaryLanguageChange: (value: string) => void;
  onSubmit: () => void;
}

const SECONDARY_ACTION_BUTTON_CLASS =
  "w-[220px] shrink-0 justify-center whitespace-nowrap text-sm font-semibold";

const RunLaunchDrawer: React.FC<RunLaunchDrawerProps> = ({
  open,
  onClose,
  deal,
  currentRunId,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canStartRun,
  canUploadDocuments,
  canLaunchRun,
  isSubmitting,
  onOpenPlaybook,
  onOpenModelConfig,
  onOpenUpload,
  onPrimaryLanguageChange,
  onSubmit,
}) => {
  const { t } = useTranslation("analysis");

  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const selectedPrimaryLanguage = deal.primary_language ?? "";
  const hasPlaybook = !!deal.playbook_version_id;

  const readinessLabel = !hasPlaybook
    ? t("runLaunch.readiness.needPlaybook")
    : hasMultipleDocumentLanguages && !selectedPrimaryLanguage
      ? t("runLaunch.readiness.needPrimaryLanguage")
      : t("runLaunch.readiness.ready");

  const handleSubmit = () => {
    if (!canLaunchRun) return;
    onSubmit();
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("runLaunch.title")}
      description={t("runLaunch.description")}
      footer={
        <div className="flex items-center justify-between gap-3">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("runLaunch.cancel")}
          </Button>

          <div className="flex items-center gap-3">
            {!canLaunchRun && (
              <span className="text-[11px] text-[var(--text-muted)]">
                {readinessLabel}
              </span>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={handleSubmit}
              disabled={!canLaunchRun}
              isLoading={isSubmitting}
            >
              {t("runLaunch.submit")}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
          <p className="text-xs font-semibold text-[var(--text-primary)]">
            {readinessLabel}
          </p>
          {currentRunId && (
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
              {t("runLaunch.previousRunHint")}
            </p>
          )}
        </div>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("runLaunch.documents.title")}
              </h4>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                {typeof documentsCount === "number"
                  ? t("runLaunch.documents.countInfo", { count: documentsCount })
                  : t("runLaunch.documents.loadingInfo")}
              </p>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                {t("runLaunch.documents.hint")}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenUpload}
              disabled={!canUploadDocuments}
              className={SECONDARY_ACTION_BUTTON_CLASS}
            >
              {t("runLaunch.documents.uploadButton")}
            </Button>
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            {t("runLaunch.checksMode.title")}
          </h4>
          <div className="mt-3 space-y-2">
            {(
              [
                {
                  value: "global_and_doc_type",
                  title: t("runLaunch.checksMode.global_and_doc_type_title"),
                  hint: t("runLaunch.checksMode.global_and_doc_type_hint"),
                },
                {
                  value: "global_only",
                  title: t("runLaunch.checksMode.global_only_title"),
                  hint: t("runLaunch.checksMode.global_only_hint"),
                },
                {
                  value: "doc_type_only",
                  title: t("runLaunch.checksMode.doc_type_only_title"),
                  hint: t("runLaunch.checksMode.doc_type_only_hint"),
                },
              ] as { value: ChecksMode; title: string; hint: string }[]
            ).map(({ value, title, hint }) => (
              <label
                key={value}
                className={[
                  "flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 transition-colors",
                  checksMode === value
                    ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                    : "border-[var(--border-soft)] bg-[var(--bg-card)] hover:bg-[var(--bg-elevated-soft)]",
                ].join(" ")}
              >
                <input
                  type="radio"
                  className="mt-[2px]"
                  value={value}
                  checked={checksMode === value}
                  onChange={() => onChecksModeChange(value)}
                  disabled={isSubmitting || !canStartRun}
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
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("runLaunch.playbook.title")}
              </h4>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {t("runLaunch.playbook.hint")}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenPlaybook}
              className={SECONDARY_ACTION_BUTTON_CLASS}
            >
              {t("runLaunch.playbook.openButton")}
            </Button>
          </div>
          <p className="mt-3 text-xs leading-5">
            {hasPlaybook ? (
              <span className="text-[var(--text-secondary)]">
                {t("runLaunch.playbook.selected")}
              </span>
            ) : (
              <span className="text-[var(--color-error-text)]">
                {t("runLaunch.playbook.notSelected")}
              </span>
            )}
          </p>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("runLaunch.modelProfile.title")}
              </h4>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {t("runLaunch.modelProfile.hint")}
              </p>
            </div>
            {onOpenModelConfig && (
              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenModelConfig}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                {t("runLaunch.modelProfile.configureButton")}
              </Button>
            )}
          </div>
          <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
            {deal.model_config_name
              ? t("runLaunch.modelProfile.current", { name: deal.model_config_name })
              : t("runLaunch.modelProfile.fallback")}
          </p>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            {t("runLaunch.primaryLanguage.title")}
          </h4>
          <div className="mt-3 flex items-center gap-2">
            <select
              className="min-w-[220px] rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:opacity-50"
              value={selectedPrimaryLanguage}
              onChange={(e) => onPrimaryLanguageChange(e.target.value)}
              disabled={documentLanguages.length === 0 || isSubmitting}
            >
              <option value="">
                {hasMultipleDocumentLanguages
                  ? t("runLaunch.primaryLanguage.placeholderMulti")
                  : t("runLaunch.primaryLanguage.placeholderAuto")}
              </option>
              {documentLanguages.map((lang) => (
                <option key={lang} value={lang}>
                  {lang}
                </option>
              ))}
            </select>
            {isSubmitting && (
              <span className="text-[11px] text-[var(--text-muted)]">
                {t("runLaunch.primaryLanguage.saving")}
              </span>
            )}
          </div>

          {documentLanguages.length > 0 && (
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              {t("runLaunch.primaryLanguage.documentLanguages", {
                list: documentLanguages.join(", "),
              })}
            </p>
          )}

          {hasMultipleDocumentLanguages && !selectedPrimaryLanguage && (
            <p className="mt-3 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2 text-[11px] leading-5 text-[var(--color-warning-text)]">
              {t("runLaunch.primaryLanguage.warningMulti")}
            </p>
          )}
        </section>

        {deal.has_pending_manual_reclassifications && (
          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">
              {t("runLaunch.extra.title")}
            </h4>
            <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-card)] px-3 py-3 text-xs text-[var(--text-secondary)]">
              <input
                type="checkbox"
                className="mt-[2px]"
                checked={forceReclassify}
                onChange={(e) => onForceReclassifyChange(e.target.checked)}
                disabled={isSubmitting}
              />
              <span>
                <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                  {t("runLaunch.extra.forceReclassifyTitle")}
                </span>
                <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                  {t("runLaunch.extra.forceReclassifyHint")}
                </span>
              </span>
            </label>
          </section>
        )}
      </div>
    </Drawer>
  );
};

export default RunLaunchDrawer;



