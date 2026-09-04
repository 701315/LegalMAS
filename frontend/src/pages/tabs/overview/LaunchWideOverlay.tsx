// =============================================================
// src/pages/tabs/overview/LaunchWideOverlay.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { Deal } from "../../../types";
import type { ChecksMode } from "../OverviewTab";

import Button from "../../../components/ui/Button";
import PipelinePreviewPanel from "./PipelinePreviewPanel";
import LaunchFormPanel from "./LaunchFormPanel";
import ProjectUploadPanel from "../../../components/upload/ProjectUploadPanel";
import DealPlaybookSelectorPanel from "../../../components/playbook/DealPlaybookSelectorPanel";
import ModelConfigManagerPanel from "../../../components/model-config/ModelConfigManagerPanel";
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../../utils/languageDiscovery";

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

interface LaunchWideOverlayProps {
  open: boolean;
  variant?: "overlay" | "inline" | "page";
  overlayWidth?: number | null;
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
  onOpenModelConfigAdminPage?: () => void;
  onPrimaryLanguageChange: (value: string) => void;
  onSubmit: () => void;
  onClose: () => void;
  onDealPatched?: (patch: Partial<Deal>) => void | Promise<void>;
}

type LeftPaneMode = "pipeline" | "upload" | "playbook" | "modelConfig";

const leftPaneShellClass =
  "flex min-w-0 min-h-0 flex-col border-r border-[var(--border-soft)] bg-[var(--bg-elevated-soft)]";

const leftPaneHeaderClass =
  "shrink-0 flex items-start justify-between gap-3 border-b border-[var(--border-soft)] px-5 py-4";

const leftPaneBodyClass =
  "min-w-0 min-h-0 flex-1 overflow-y-auto px-5 py-4";

const rightPaneClass =
  "min-w-0 min-h-0 overflow-y-auto bg-[var(--bg-card)]";

const leftPaneShellInlineClass =
  "order-2 flex min-w-0 min-h-0 flex-col border-t border-[var(--border-soft)] bg-[var(--bg-elevated-soft)]";

const rightPaneInlineClass = "order-1 min-w-0 min-h-0 bg-[var(--bg-card)]";

const pageShellClass =
  "flex min-w-0 min-h-0 flex-col bg-[var(--bg-elevated-soft)]";

function getReadinessLabel(
  params: {
    hasCurrentRun: boolean;
    hasDocuments: boolean;
    hasPlaybook: boolean;
    hasLanguagesReady: boolean;
    hasPrimaryLanguage: boolean;
    isSubmitting: boolean;
    discoveryStatus: string | null;
  },
  tFn: TranslateFn,
): string | null {
  const {
    hasCurrentRun,
    hasDocuments,
    hasPlaybook,
    hasLanguagesReady,
    hasPrimaryLanguage,
    isSubmitting,
    discoveryStatus,
  } = params;

  if (!hasDocuments) {
    return tFn("overviewPanels.launchOverlay.readiness.noDocs");
  }

  if (!hasPlaybook) {
    return hasCurrentRun
      ? tFn("overviewPanels.launchOverlay.readiness.noPlaybookRelaunch")
      : tFn("overviewPanels.launchOverlay.readiness.noPlaybookLaunch");
  }

  if (!hasLanguagesReady) {
    if (discoveryStatus === "processing") {
      return tFn("overviewPanels.launchOverlay.readiness.discoveryProcessing");
    }

    if (discoveryStatus === "pending") {
      return tFn("overviewPanels.launchOverlay.readiness.discoveryPending");
    }

    if (discoveryStatus === "failed") {
      return tFn("overviewPanels.launchOverlay.readiness.discoveryFailed");
    }

    if (discoveryStatus === "partial") {
      return tFn("overviewPanels.launchOverlay.readiness.discoveryPartial");
    }

    return tFn("overviewPanels.launchOverlay.readiness.discoveryPreparing");
  }

  if (!hasPrimaryLanguage) {
    return hasCurrentRun
      ? tFn("overviewPanels.launchOverlay.readiness.noPrimaryLangRelaunch")
      : tFn("overviewPanels.launchOverlay.readiness.noPrimaryLangLaunch");
  }

  if (isSubmitting) {
    return hasCurrentRun
      ? tFn("overviewPanels.launchOverlay.readiness.submittingRelaunch")
      : tFn("overviewPanels.launchOverlay.readiness.submittingLaunch");
  }

  return null;
}

interface LeftPaneHeaderProps {
  category: string;
  title: string;
  description: string;
  onBack: () => void;
  backText: string;
}

const LeftPaneHeader: React.FC<LeftPaneHeaderProps> = ({
  category,
  title,
  description,
  onBack,
  backText,
}) => (
  <div className={leftPaneHeaderClass}>
    <div className="min-w-0">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {category}
      </p>
      <h3 className="text-base font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">{description}</p>
    </div>

    <Button variant="secondary" size="sm" onClick={onBack}>
      {backText}
    </Button>
  </div>
);

const LaunchWideOverlay: React.FC<LaunchWideOverlayProps> = ({
  open,
  variant = "overlay",
  overlayWidth,
  deal,
  hasCurrentRun,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canStartRun,
  canUploadDocuments,
  isSubmitting,
  onOpenModelConfigAdminPage,
  onPrimaryLanguageChange,
  onSubmit,
  onClose,
  onDealPatched,
}) => {
  const { t } = useTranslation("projects");
  const [leftPaneMode, setLeftPaneMode] =
    React.useState<LeftPaneMode>("pipeline");

  React.useEffect(() => {
    if (open) {
      setLeftPaneMode("pipeline");
    }
  }, [open]);

  const uniqueDocumentLanguages = React.useMemo(
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

  const selectedPrimaryLanguage = React.useMemo(
    () => normalizeLang(deal.primary_language),
    [deal.primary_language],
  );

  const discoveryStatus = React.useMemo(
    () => normalizeDiscoveryStatus(deal.language_discovery_status),
    [deal.language_discovery_status],
  );

  const hasLanguagesReady = uniqueDocumentLanguages.length > 0;
  const hasPlaybook = !!deal.playbook_version_id;
  const hasPrimaryLanguage = !!selectedPrimaryLanguage;
  const hasDocuments =
    typeof documentsCount === "number" ? documentsCount > 0 : false;

  const readinessLabel = React.useMemo(
    () =>
      getReadinessLabel(
        {
          hasCurrentRun,
          hasDocuments,
          hasPlaybook,
          hasLanguagesReady,
          hasPrimaryLanguage,
          isSubmitting,
          discoveryStatus,
        },
        t,
      ),
    [
      hasCurrentRun,
      hasDocuments,
      hasPlaybook,
      hasLanguagesReady,
      hasPrimaryLanguage,
      isSubmitting,
      discoveryStatus,
      t,
    ],
  );

  const handleBackToPipeline = React.useCallback(() => {
    setLeftPaneMode("pipeline");
  }, []);

  const handleOpenUploadPanel = React.useCallback(() => {
    if (!canUploadDocuments) return;
    setLeftPaneMode("upload");
  }, [canUploadDocuments]);

  const handleOpenPlaybookPanel = React.useCallback(() => {
    setLeftPaneMode("playbook");
  }, []);

  const handleOpenModelConfigPanel = React.useCallback(() => {
    setLeftPaneMode("modelConfig");
  }, []);

  const handleUploadFinished = React.useCallback(async () => {
    handleBackToPipeline();
    await onDealPatched?.({});
  }, [handleBackToPipeline, onDealPatched]);

  if (!open) {
    return null;
  }

  const isOverlay = variant === "overlay";
  const isPage = variant === "page";

  if (isOverlay && (overlayWidth ?? 0) <= 0) {
    return null;
  }

  const shellClass = isPage
    ? pageShellClass
    : isOverlay
      ? leftPaneShellClass
      : leftPaneShellInlineClass;
  const rightPaneCls = isOverlay ? rightPaneClass : rightPaneInlineClass;

  const overlayCategory = hasCurrentRun
    ? t("overviewPanels.launchOverlay.categoryRelaunch")
    : t("overviewPanels.launchOverlay.categoryLaunch");
  const overlayTitle = hasCurrentRun
    ? t("overviewPanels.launchOverlay.titleRelaunch")
    : t("overviewPanels.launchOverlay.titleLaunch");
  const overlayDescription = hasCurrentRun
    ? t("overviewPanels.launchOverlay.descRelaunch")
    : t("overviewPanels.launchOverlay.descLaunch");
  const submitButtonLabel = hasCurrentRun
    ? t("overviewPanels.launchOverlay.submitRelaunch")
    : t("overviewPanels.launchOverlay.submitLaunch");
  const backText = t("overviewPanels.launchOverlay.subpanes.toSummary");

  const renderUploadPane = () => (
    <div className={shellClass}>
      <LeftPaneHeader
        category={t("overviewPanels.launchOverlay.subpanes.upload.category")}
        title={t("overviewPanels.launchOverlay.subpanes.upload.title")}
        description={
          hasCurrentRun
            ? t("overviewPanels.launchOverlay.subpanes.upload.descRelaunch")
            : t("overviewPanels.launchOverlay.subpanes.upload.descLaunch")
        }
        onBack={handleBackToPipeline}
        backText={backText}
      />
      <div className={leftPaneBodyClass}>
        <ProjectUploadPanel
          dealId={deal.id}
          mode="embedded"
          showWorkflow={false}
          onFinished={handleUploadFinished}
        />
      </div>
    </div>
  );

  const renderPlaybookPane = () => (
    <div className={shellClass}>
      <LeftPaneHeader
        category={t("overviewPanels.launchOverlay.subpanes.playbook.category")}
        title={t("overviewPanels.launchOverlay.subpanes.playbook.title")}
        description={
          hasCurrentRun
            ? t("overviewPanels.launchOverlay.subpanes.playbook.descRelaunch")
            : t("overviewPanels.launchOverlay.subpanes.playbook.descLaunch")
        }
        onBack={handleBackToPipeline}
        backText={backText}
      />
      <div className={leftPaneBodyClass}>
        <DealPlaybookSelectorPanel
          dealId={deal.id}
          deal={deal}
          mode="embedded"
          onCancel={handleBackToPipeline}
          onFinished={handleBackToPipeline}
          onDealPatched={onDealPatched}
        />
      </div>
    </div>
  );

  const renderModelConfigPane = () => (
    <div className={shellClass}>
      <LeftPaneHeader
        category={t("overviewPanels.launchOverlay.subpanes.modelConfig.category")}
        title={t("overviewPanels.launchOverlay.subpanes.modelConfig.title")}
        description={t("overviewPanels.launchOverlay.subpanes.modelConfig.desc")}
        onBack={handleBackToPipeline}
        backText={backText}
      />
      <div className={leftPaneBodyClass}>
        <ModelConfigManagerPanel
          mode="embedded"
          dealId={deal.id}
          currentDeal={deal}
          onDealPatched={onDealPatched}
          onFinished={handleBackToPipeline}
          onCancel={handleBackToPipeline}
          onOpenPlaybookVersions={(modelConfigId) => {
            if (onOpenModelConfigAdminPage) {
              onOpenModelConfigAdminPage();
              return;
            }

            window.open(
              `/admin/playbook-versions?modelConfigId=${encodeURIComponent(
                modelConfigId,
              )}`,
              "_blank",
              "noopener,noreferrer",
            );
          }}
        />
      </div>
    </div>
  );

  const renderPipelinePane = () => (
    <div className={shellClass}>
      <div className={leftPaneBodyClass}>
        <PipelinePreviewPanel
          deal={deal}
          hasCurrentRun={hasCurrentRun}
          documentsCount={documentsCount}
          checksMode={checksMode}
          forceReclassify={forceReclassify}
        />
      </div>
    </div>
  );

  const renderLeftPane = () => {
    switch (leftPaneMode) {
      case "upload":
        return renderUploadPane();
      case "playbook":
        return renderPlaybookPane();
      case "modelConfig":
        return renderModelConfigPane();
      case "pipeline":
      default:
        return renderPipelinePane();
    }
  };

  if (isPage) {
    return (
      <div className="flex min-h-0 flex-col gap-3">
        {readinessLabel && (
          <div className="shrink-0 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-2">
            <p className="text-xs font-medium text-[var(--color-warning-text)]">
              {readinessLabel}
            </p>
          </div>
        )}

        <div className="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="min-h-0 min-w-0 rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-card)]">
            <LaunchFormPanel
              deal={deal}
              hasCurrentRun={hasCurrentRun}
              documentsCount={documentsCount}
              checksMode={checksMode}
              onChecksModeChange={onChecksModeChange}
              forceReclassify={forceReclassify}
              onForceReclassifyChange={onForceReclassifyChange}
              canStartRun={canStartRun}
              canUploadDocuments={canUploadDocuments}
              isSubmitting={isSubmitting}
              onOpenPlaybook={handleOpenPlaybookPanel}
              onOpenModelConfig={handleOpenModelConfigPanel}
              onOpenUpload={handleOpenUploadPanel}
              onPrimaryLanguageChange={onPrimaryLanguageChange}
            />
          </div>

          <div className="min-h-0 min-w-0 rounded-2xl border border-[var(--border-soft)]">
            {renderLeftPane()}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={
        isOverlay
          ? "absolute bottom-0 top-0 z-30 hidden xl:block right-[calc(100%+16px)]"
          : "relative w-full"
      }
      style={isOverlay ? { width: overlayWidth ?? undefined } : undefined}
    >
      <section
        className={
          isOverlay
            ? "flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl"
            : "flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl"
        }
      >
        <div className="shrink-0 border-b border-[var(--border-soft)] px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {overlayCategory}
              </p>
              <h3 className="text-base font-semibold text-[var(--text-primary)]">
                {overlayTitle}
              </h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {overlayDescription}
              </p>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="shrink-0 rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
              aria-label={t("actions.close", { ns: "common", defaultValue: "Close" })}
            >
              ✕
            </button>
          </div>
        </div>

        <div
          className={
            isOverlay ? "grid min-h-0 flex-1" : "grid min-h-0 grid-cols-1"
          }
          style={isOverlay ? { gridTemplateColumns: "3fr 2fr" } : undefined}
        >
          {renderLeftPane()}
          <div className={rightPaneCls}>
            <LaunchFormPanel
              deal={deal}
              hasCurrentRun={hasCurrentRun}
              documentsCount={documentsCount}
              checksMode={checksMode}
              onChecksModeChange={onChecksModeChange}
              forceReclassify={forceReclassify}
              onForceReclassifyChange={onForceReclassifyChange}
              canStartRun={canStartRun}
              canUploadDocuments={canUploadDocuments}
              isSubmitting={isSubmitting}
              onOpenPlaybook={handleOpenPlaybookPanel}
              onOpenModelConfig={handleOpenModelConfigPanel}
              onOpenUpload={handleOpenUploadPanel}
              onPrimaryLanguageChange={onPrimaryLanguageChange}
            />
          </div>
        </div>

        <div className="shrink-0 flex items-center justify-between gap-4 border-t border-[var(--border-soft)] bg-[var(--bg-card)] px-5 py-4">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("actions.cancel", { ns: "common", defaultValue: "Cancel" })}
          </Button>

          <div className="flex min-w-0 items-center gap-3">
            {readinessLabel && (
              <span className="truncate text-[11px] text-[var(--text-muted)]">
                {readinessLabel}
              </span>
            )}

            <Button
              variant="secondary"
              size="sm"
              onClick={onSubmit}
              disabled={!canStartRun || isSubmitting}
              isLoading={isSubmitting}
            >
              {submitButtonLabel}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LaunchWideOverlay;


