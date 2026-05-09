// =============================================================
// src/pages/tabs/overview/LaunchWideOverlay.tsx
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import type { ChecksMode } from "../OverviewTab";

import Button from "../../../components/ui/Button";
import PipelinePreviewPanel from "./PipelinePreviewPanel";
import LaunchFormPanel from "./LaunchFormPanel";
import ProjectUploadPanel from "../../../components/upload/ProjectUploadPanel";
import DealPlaybookSelectorPanel from "../../../components/playbook/DealPlaybookSelectorPanel";
import ModelConfigManagerPanel from "../../../components/model-config/ModelConfigManagerPanel";

interface LaunchWideOverlayProps {
  open: boolean;
  overlayWidth: number;
  deal: Deal;
  latestRunId?: string | null;
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
  onDealPatched?: (patch: Partial<Deal>) => void;
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

const LaunchWideOverlay: React.FC<LaunchWideOverlayProps> = ({
  open,
  overlayWidth,
  deal,
  latestRunId,
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
  const [leftPaneMode, setLeftPaneMode] =
    React.useState<LeftPaneMode>("pipeline");

  React.useEffect(() => {
    if (open) {
      setLeftPaneMode("pipeline");
    }
  }, [open]);

  if (!open || overlayWidth <= 0) return null;

  const hasPlaybook = !!deal.playbook_version_id;
  const hasPrimaryLanguage = !!deal.primary_language;

  const canLaunchRun =
    canStartRun &&
    hasPlaybook &&
    hasPrimaryLanguage &&
    !isSubmitting;

  const readinessLabel = !hasPlaybook
    ? "Нужно выбрать playbook, чтобы запустить анализ."
    : !hasPrimaryLanguage
      ? "Нужно выбрать основной язык анализа."
      : "Параметры готовы к запуску анализа.";

  const handleOpenUploadPanel = () => {
    if (!canUploadDocuments) return;
    setLeftPaneMode("upload");
  };

  const handleOpenPlaybookPanel = () => {
    setLeftPaneMode("playbook");
  };

  const handleOpenModelConfigPanel = () => {
    setLeftPaneMode("modelConfig");
  };

  const handleBackToPipeline = () => {
    setLeftPaneMode("pipeline");
  };

  const renderUploadPane = () => {
    return (
      <div className={leftPaneShellClass}>
        <div className={leftPaneHeaderClass}>
          <div className="min-w-0">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Upload
            </p>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">
              Загрузка документов
            </h3>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Подготовьте набор файлов, загрузите документы в проект и вернитесь
              к запуску анализа.
            </p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleBackToPipeline}
          >
            К сценарию
          </Button>
        </div>

        <div className={leftPaneBodyClass}>
          <ProjectUploadPanel
            dealId={deal.id}
            mode="embedded"
            showWorkflow={false}
            onFinished={handleBackToPipeline}
          />
        </div>
      </div>
    );
  };

  const renderPlaybookPane = () => {
    return (
      <div className={leftPaneShellClass}>
        <div className={leftPaneHeaderClass}>
          <div className="min-w-0">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Playbook
            </p>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">
              Выбор playbook проекта
            </h3>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Выберите шаблон и версию playbook для этого проекта, затем
              вернитесь к параметрам запуска анализа.
            </p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleBackToPipeline}
          >
            К сценарию
          </Button>
        </div>

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
  };

  const renderModelConfigPane = () => {
    return (
      <div className={leftPaneShellClass}>
        <div className={leftPaneHeaderClass}>
          <div className="min-w-0">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Model profile
            </p>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">
              Профиль модели
            </h3>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Выберите или отредактируйте профиль модели для этой сделки.
            </p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleBackToPipeline}
          >
            К сценарию
          </Button>
        </div>

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
  };

  const renderPipelinePane = () => {
    return (
      <div className={leftPaneShellClass}>
        <div className={leftPaneBodyClass}>
          <PipelinePreviewPanel
            deal={deal}
            documentsCount={documentsCount}
            checksMode={checksMode}
            forceReclassify={forceReclassify}
          />
        </div>
      </div>
    );
  };

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

  return (
    <div
      className="
        absolute top-0 bottom-0 z-30 hidden xl:block
        right-[calc(100%+16px)]
      "
      style={{ width: overlayWidth }}
    >
      <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        <div className="shrink-0 border-b border-[var(--border-soft)] px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Analysis launch
              </p>
              <h3 className="text-base font-semibold text-[var(--text-primary)]">
                Подготовка запуска анализа
              </h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Слева — сценарий пайплайна, загрузка документов, выбор playbook
                или профиля модели; справа — параметры запуска.
              </p>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
              aria-label="Закрыть панель запуска анализа"
            >
              ✕
            </button>
          </div>
        </div>

        <div
          className="grid min-h-0 flex-1"
          style={{ gridTemplateColumns: "3fr 2fr" }}
        >
          {renderLeftPane()}

          <div className={rightPaneClass}>
            <LaunchFormPanel
              deal={deal}
              latestRunId={latestRunId}
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
            Отмена
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
              onClick={onSubmit}
              disabled={!canLaunchRun}
              isLoading={isSubmitting}
            >
              Запустить анализ
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LaunchWideOverlay;



