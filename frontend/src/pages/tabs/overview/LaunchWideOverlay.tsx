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
  /**
   * "overlay" (default, xl+): absolute относительно rail wrapper,
   * width = overlayWidth, торчит влево на main column.
   * "inline" (<xl): in-flow панель в mobile-ветке OverviewTab:
   * full width, вертикальный стек (форма первая), overlayWidth игнорируется.
   * "page": встроенный двухколоночный режим для вкладки перезапуска:
   * левая колонка — форма запуска, правая — preview/subpanes.
   * Внешний header/footer не рендерятся (живут в карточке RelaunchContent).
   */
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

// inline (<xl): panes стекуются вертикально. Форма (right pane) — первая
// через order, т.к. это primary task; preview/subpanes ниже.
// Разделитель горизонтальный (border-t) вместо вертикального (border-r).
const leftPaneShellInlineClass =
  "order-2 flex min-w-0 min-h-0 flex-col border-t border-[var(--border-soft)] bg-[var(--bg-elevated-soft)]";

const rightPaneInlineClass = "order-1 min-w-0 min-h-0 bg-[var(--bg-card)]";

// page: panes без внутренних боковых границ — каждая колонка
// обёрнута в собственную карточку на уровне page-рендера.
const pageShellClass =
  "flex min-w-0 min-h-0 flex-col bg-[var(--bg-elevated-soft)]";

function getReadinessLabel(params: {
  hasCurrentRun: boolean;
  hasDocuments: boolean;
  hasPlaybook: boolean;
  hasLanguagesReady: boolean;
  hasPrimaryLanguage: boolean;
  isSubmitting: boolean;
  discoveryStatus: string | null;
}): string | null {
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
    return "Сначала загрузите документы в проект.";
  }

  if (!hasPlaybook) {
    return hasCurrentRun
      ? "Нужно выбрать playbook перед перезапуском."
      : "Нужно выбрать playbook перед запуском.";
  }

  if (!hasLanguagesReady) {
    if (discoveryStatus === "processing") {
      return "Языки документов ещё определяются.";
    }

    if (discoveryStatus === "pending") {
      return "Подготовка определения языков ещё не завершена.";
    }

    if (discoveryStatus === "failed") {
      return "Не удалось определить языки документов.";
    }

    if (discoveryStatus === "partial") {
      return "Языки определены не для всех документов. Проверьте файлы.";
    }

    return "Подготавливаем языки документов.";
  }

  if (!hasPrimaryLanguage) {
    return hasCurrentRun
      ? "Нужно выбрать основной язык перед перезапуском."
      : "Нужно выбрать основной язык перед запуском.";
  }

  if (isSubmitting) {
    return hasCurrentRun ? "Запускаем новый прогон…" : "Запускаем анализ…";
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
      К сводке
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
        hasCurrentRun,
        hasDocuments,
        hasPlaybook,
        hasLanguagesReady,
        hasPrimaryLanguage,
        isSubmitting,
        discoveryStatus,
      }),
    [
      hasCurrentRun,
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

  if (!open) {
    return null;
  }

  const isOverlay = variant === "overlay";
  const isPage = variant === "page";

  // overlay-variant бессмысленен без вычисленной ширины;
  // inline и page игнорируют overlayWidth.
  if (isOverlay && (overlayWidth ?? 0) <= 0) {
    return null;
  }

  const shellClass = isPage
    ? pageShellClass
    : isOverlay
      ? leftPaneShellClass
      : leftPaneShellInlineClass;
  const rightPaneCls = isOverlay ? rightPaneClass : rightPaneInlineClass;

  const overlayCategory = hasCurrentRun ? "Повторный анализ" : "Новый анализ";
  const overlayTitle = hasCurrentRun ? "Перезапуск анализа" : "Запуск анализа";
  const overlayDescription = hasCurrentRun
    ? "Проверьте документы и текущие настройки проекта перед новым прогоном."
    : "Проверьте документы и настройки проекта перед первым запуском.";
  const submitButtonLabel = hasCurrentRun
    ? "Перезапустить анализ"
    : "Запустить анализ";

  const renderUploadPane = () => (
    <div className={shellClass}>
      <LeftPaneHeader
        category="Upload"
        title="Загрузка документов"
        description={
          hasCurrentRun
            ? "Добавьте документы в проект и вернитесь к параметрам перезапуска."
            : "Добавьте документы в проект и вернитесь к параметрам запуска."
        }
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
    <div className={shellClass}>
      <LeftPaneHeader
        category="Playbook"
        title="Выбор playbook проекта"
        description={
          hasCurrentRun
            ? "Выберите playbook проекта и вернитесь к параметрам перезапуска."
            : "Выберите playbook проекта и вернитесь к параметрам запуска."
        }
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
    <div className={shellClass}>
      <LeftPaneHeader
        category="Model profile"
        title="Профиль модели"
        description="Выберите или обновите профиль модели, затем вернитесь к параметрам анализа."
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

  // ── page variant: двухколоночный встроенный режим ─────────────────
  // Левая колонка — форма запуска (LaunchFormPanel), правая — preview
  // или активный subpane (Upload / Playbook / ModelConfig).
  // Внешний header/footer не рендерятся: заголовок страницы и кнопки
  // живут в карточке RelaunchContent (DealPage).
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
          {/* Левая колонка — форма запуска.
              Не имеет собственного overflow-y-auto — прокрутка
              делегирована внешнему контейнеру RelaunchContent. */}
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

          {/* Правая колонка — preview / subpanes.
              Не имеет собственного overflow-y-auto — прокрутка
              делегирована внешнему контейнеру RelaunchContent. */}
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
              aria-label="Закрыть панель анализа"
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
              {submitButtonLabel}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LaunchWideOverlay;