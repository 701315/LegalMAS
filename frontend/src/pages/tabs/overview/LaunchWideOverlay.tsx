// =============================================================
// src/pages/tabs/overview/LaunchWideOverlay.tsx
// Launch panel раскрывается до границы основной контентной колонки,
// без backdrop и без перекрытия AnalysisActionsPanel.
// Ширина overlay вычисляется от реального layout, а не от 100vw.
//
// Актуальный контракт:
// - overlay не принимает run id;
// - current run остаётся на уровне OverviewTab;
// - панель запуска работает только с параметрами запуска и deal state.
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
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../../utils/languageDiscovery";

interface LaunchWideOverlayProps {
  open: boolean;
  overlayWidth: number;
  deal: Deal;
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

function getReadinessLabel(params: {
  hasDocuments: boolean;
  hasPlaybook: boolean;
  hasLanguagesReady: boolean;
  hasPrimaryLanguage: boolean;
  isSubmitting: boolean;
  discoveryStatus: string | null;
}): string | null {
  const {
    hasDocuments,
    hasPlaybook,
    hasLanguagesReady,
    hasPrimaryLanguage,
    isSubmitting,
    discoveryStatus,
  } = params;

  if (!hasDocuments) {
    return "Сначала загрузите документы в проект.";
  }

  if (!hasPlaybook) {
    return "Нужно выбрать playbook, чтобы запустить анализ.";
  }

  if (!hasLanguagesReady) {
    if (discoveryStatus === "processing") {
      return "Языки документов ещё определяются. Запуск станет доступен после завершения language discovery.";
    }

    if (discoveryStatus === "pending") {
      return "Подготовка language discovery ещё не завершена. Запуск станет доступен после определения языков документов.";
    }

    if (discoveryStatus === "failed") {
      return "Не удалось автоматически определить языки документов. Проверьте импорт или повторите подготовку.";
    }

    if (discoveryStatus === "partial") {
      return "Языки определены частично. Проверьте набор документов перед запуском анализа.";
    }

    return "Подготавливаем языки документов. Запуск станет доступен после определения языка.";
  }

  if (!hasPrimaryLanguage) {
    return "Нужно выбрать основной язык анализа.";
  }

  if (isSubmitting) {
    return "Выполняем запрос…";
  }

  return null;
}

interface LeftPaneHeaderProps {
  category: string;
  title: string;
  description: string;
  onBack: () => void;
}

const LeftPaneHeader: React.FC<LeftPaneHeaderProps> = ({
  category,
  title,
  description,
  onBack,
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
      К сценарию
    </Button>
  </div>
);

const LaunchWideOverlay: React.FC<LaunchWideOverlayProps> = ({
  open,
  overlayWidth,
  deal,
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
      getReadinessLabel({
        hasDocuments,
        hasPlaybook,
        hasLanguagesReady,
        hasPrimaryLanguage,
        isSubmitting,
        discoveryStatus,
      }),
    [
      hasDocuments,
      hasPlaybook,
      hasLanguagesReady,
      hasPrimaryLanguage,
      isSubmitting,
      discoveryStatus,
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

  if (!open || overlayWidth <= 0) {
    return null;
  }

  const renderUploadPane = () => (
    <div className={leftPaneShellClass}>
      <LeftPaneHeader
        category="Upload"
        title="Загрузка документов"
        description="Подготовьте набор файлов, загрузите документы в проект и вернитесь к запуску анализа."
        onBack={handleBackToPipeline}
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
    <div className={leftPaneShellClass}>
      <LeftPaneHeader
        category="Playbook"
        title="Выбор playbook проекта"
        description="Выберите шаблон и версию playbook для этого проекта, затем вернитесь к параметрам запуска анализа."
        onBack={handleBackToPipeline}
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
    <div className={leftPaneShellClass}>
      <LeftPaneHeader
        category="Model profile"
        title="Профиль модели"
        description="Выберите или отредактируйте профиль модели для этой сделки."
        onBack={handleBackToPipeline}
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
      className="absolute bottom-0 top-0 z-30 hidden xl:block right-[calc(100%+16px)]"
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
              className="shrink-0 rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
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
              Запустить анализ
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LaunchWideOverlay;



