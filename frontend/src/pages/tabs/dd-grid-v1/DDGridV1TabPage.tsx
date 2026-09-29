// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1TabPage.tsx
// V1 экран DD Grid.
//
// Актуальное состояние:
// - Блок "DD Grid" убран, сводка перенесена в subtitle секции;
// - В matrix mode subtitle показывает компактную сводку статистики;
// - В list mode subtitle остаётся стандартным;
// - Warning об ошибке run metadata показывается сверху при необходимости;
// - Панель настроек отображения (Формат / Проверки / Группировка) + Экспорт;
// - QC bulk actions под панелью;
// - Grid viewport с V1 матрицей или legacy списком;
// - Фильтры полностью убраны из UI (могут быть возвращены позже).
//
// i18n: все UI-строки через namespace "ddGrid", ключи v1Tab.*
// =============================================================

import React from "react";
import { useTranslation, Trans } from "react-i18next";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Download,
  SlidersHorizontal,
} from "lucide-react";

import { useDealReviewDdGridV1 } from "../../../api/dealReview";
import { useAuth } from "../../../hooks/useAuth";
import { useRun } from "../../../api/runs";
import client from "../../../api/client";
import DDGridV1TypedGroups from "./DDGridV1TypedGroups";
import DDGridV1List, {
  DD_GRID_V1_EXTRA_COLUMNS,
} from "./DDGridV1List";
import DDGridV1ViewSettings from "./DDGridV1ViewSettings";
import { useDDGridV1UIStore } from "./ddGridV1.collapseStore";
import Button from "../../../components/ui/Button";
import DocumentViewerModal, {
  type LayoutElement,
  type SizedChunkMeta,
} from "../../../components/viewer/DocumentViewerModal";

import type { OpenViewerAtFn } from "../../../types";

import { INLINE_PANEL_ACTIVE_CLASS } from "../grid/gridTab.constants";
import { humanChecksMode } from "../grid/gridTab.utils";
import type {
  GridMode,
  GridTabProps,
  ViewerState,
} from "../grid/gridTab.types";
import type { ReviewSelectionItem } from "./ddGridV1.types";
import DDGridV1ExportButtons from "./DDGridV1ExportButtons";
import DDGridV1ExportLayoutPicker, {
  type DDGridV1MatrixLayout,
} from "./DDGridV1ExportLayoutPicker";
import {
  buildDDGridV1MatrixExportTable,
  buildDDGridV1DocumentSectionedExportTable,
  buildDDGridV1ScopeGroupSectionedExportTable,
} from "./ddGridV1.exportBuilder";
import {
  exportMatrixSingleToPdf,
  exportMatrixSingleToWord,
  exportSectionedToPdf,
  exportSectionedToWord,
} from "./ddGridV1.exportRunners";
import {
  getSelectedV1Drawers,
  getV1QcCapability,
  getV1QcDisabledNote,
} from "./ddGridV1.qc";
import DDGridV1QcBulkActions from "./DDGridV1QcBulkActions";
import ResultPresentationStatus from "./ResultPresentationStatus";

import { selectDDGridV1DerivedModel } from "./ddGridV1.selectors";
import { useIsMobile } from "../../../hooks/useIsMobile";

// -------------------------------------------------------------
// Local types
// -------------------------------------------------------------

type LayoutElementApi = {
  element_id: string;
  page: number;
  bbox: [number, number, number, number];
};

type StatusStateCardProps = {
  title: string;
  description?: string;
  tone?: "default" | "error";
};

type RunMetaWarningProps = {
  visible: boolean;
};

type ExportPanelProps = {
  open: boolean;
  model: import("./ddGridV1.types").DDGridV1DerivedModel;
  mode: "list" | "matrix";
  visibleCheckIds?: readonly string[];
  includePassResults?: boolean;
  visibleExtraColumnIds?: readonly string[];
  dealName: string;
  runId?: string;
  /** true если inline layout picker сейчас показан. */
  layoutPickerFormat: "pdf" | "docx" | null;
  onRequestLayoutPicker: (format: "pdf" | "docx") => void;
  onCancelLayoutPicker: () => void;
  onApplyLayout: (
    format: "pdf" | "docx",
    layout: DDGridV1MatrixLayout,
  ) => void;
};

// -------------------------------------------------------------
// Pure helpers
// -------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isBboxTuple(
  value: unknown,
): value is [number, number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every((item) => typeof item === "number")
  );
}

function isLayoutElementApi(value: unknown): value is LayoutElementApi {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.element_id === "string" &&
    typeof value.page === "number" &&
    isBboxTuple(value.bbox)
  );
}

function parseLayoutElements(payload: unknown): LayoutElement[] | undefined {
  if (!isRecord(payload) || !Array.isArray(payload.elements)) {
    return undefined;
  }
  return payload.elements
    .filter(isLayoutElementApi)
    .map((element) => ({
      elementId: element.element_id,
      page: element.page,
      bbox: element.bbox,
    }));
}

function parseSizedChunks(payload: unknown): SizedChunkMeta[] | undefined {
  if (!isRecord(payload) || !Array.isArray(payload.chunks)) {
    return undefined;
  }
  return payload.chunks
    .filter(isRecord)
    .map((chunk) => ({
      id: String(chunk.id ?? ""),
      elementIds: Array.isArray(chunk.element_ids)
        ? chunk.element_ids.map(String)
        : [],
      clauseUids: Array.isArray(chunk.clause_uids)
        ? chunk.clause_uids.map(String)
        : [],
    }))
    .filter((chunk) => chunk.id.length > 0);
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

// -------------------------------------------------------------
// DD Grid header summary — компактная строка со статистикой
// -------------------------------------------------------------

interface DDGridV1SummaryLineProps {
  documentsCount: number;
  checksCount: number;
  findingsCount: number;
  runtimeColsCount: number;
  definedCellsCount: number;
  notDefinedCellsCount: number;
  errorCellsCount: number;
  checksMode: string | null;
  className?: string;
}

const DDGridV1SummaryLine: React.FC<DDGridV1SummaryLineProps> = ({
  documentsCount,
  checksCount,
  findingsCount,
  runtimeColsCount,
  definedCellsCount,
  notDefinedCellsCount,
  errorCellsCount,
  checksMode,
  className,
}) => {
  const { t } = useTranslation("ddGrid");

  const docsText = t("v1Tab.summary.documentsCount", { count: documentsCount });
  const checksText = t("v1Tab.summary.checksCount", { count: checksCount });
  const findingsText = t("v1Tab.summary.findingsCount", { count: findingsCount });
  const modeText = checksMode ?? t("v1Tab.summary.modeNotSpecified");

  const tooltip = [
    t("v1Tab.summary.tooltipRuntime", { count: runtimeColsCount }),
    t("v1Tab.summary.tooltipCells", {
      defined: definedCellsCount,
      notFound: notDefinedCellsCount,
      errors: errorCellsCount,
    }),
  ].join("\n");

  const rootClassName =
    className ?? "text-sm leading-6 text-[var(--text-secondary)]";

  return (
    <p className={rootClassName} title={tooltip}>
      <Trans
        i18nKey="v1Tab.summary.line"
        ns="ddGrid"
        values={{
          documents: docsText,
          checks: checksText,
          findings: findingsText,
          mode: modeText,
        }}
        components={{
          bold: <span className="font-semibold text-[var(--text-primary)]" />,
        }}
      />
    </p>
  );
};

// -------------------------------------------------------------
// Sub-components
// -------------------------------------------------------------

const StatusStateCard: React.FC<StatusStateCardProps> = ({
  title,
  description,
  tone = "default",
}) => {
  if (tone === "error") {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3 text-sm text-[var(--color-error-text)]">
            <div>{title}</div>
            {description ? <p className="mt-0">{description}</p> : null}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="px-6 py-10">
        <div className="flex min-h-[280px] flex-col items-center justify-center text-center">
          <div className="text-base font-semibold text-[var(--text-primary)]">
            {title}
          </div>
          {description ? (
            <p className="mt-2 max-w-md text-sm text-[var(--text-muted)]">
              {description}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
};

const RunMetaWarning: React.FC<RunMetaWarningProps> = ({ visible }) => {
  const { t } = useTranslation("ddGrid");

  if (!visible) {
    return null;
  }

  return (
    <div className="flex items-start gap-2 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3 text-sm text-[var(--color-warning-text)]">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{t("v1Tab.runMetaWarning")}</span>
    </div>
  );
};

const ExportPanel: React.FC<ExportPanelProps> = ({
  open,
  model,
  mode,
  visibleCheckIds,
  includePassResults,
  visibleExtraColumnIds,
  dealName,
  runId,
  layoutPickerFormat,
  onRequestLayoutPicker,
  onCancelLayoutPicker,
  onApplyLayout,
}) => {
  const { t } = useTranslation("ddGrid");

  const modeDescription =
    mode === "matrix"
      ? t("v1Tab.export.matrixDescription")
      : t("v1Tab.export.listDescription");

  const modeLabel =
    mode === "matrix"
      ? t("v1Tab.export.modeMatrix")
      : t("v1Tab.export.modeList");

  return (
    <div
      id="dd-grid-v1-export-panel"
      aria-hidden={!open}
      className={`grid overflow-hidden transition-[grid-template-rows,opacity,margin] duration-300 ease-out ${
        open
          ? "mt-3 grid-rows-[1fr] opacity-100"
          : "mt-0 grid-rows-[0fr] opacity-0"
      }`}
    >
      <div className="min-h-0">
        <div className="flex flex-col gap-3">
          {/* ── Основная панель с кнопками экспорта ──────────── */}
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  {t("v1Tab.export.panelTitle", { mode: modeLabel })}
                </p>
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                  {modeDescription}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <DDGridV1ExportButtons
                  model={model}
                  mode={mode}
                  visibleCheckIds={visibleCheckIds}
                  includePassResults={includePassResults}
                  visibleExtraColumnIds={visibleExtraColumnIds}
                  dealName={dealName}
                  runId={runId}
                  onRequestMatrixLayout={onRequestLayoutPicker}
                  activeLayoutPickerFormat={layoutPickerFormat}
                />
              </div>
            </div>
          </div>

          {/* ── Inline layout picker (только matrix + после клика PDF/Word) ── */}
          <div
            className={`grid overflow-hidden transition-[grid-template-rows,opacity] duration-300 ease-out ${
              layoutPickerFormat
                ? "grid-rows-[1fr] opacity-100"
                : "grid-rows-[0fr] opacity-0"
            }`}
          >
            <div className="min-h-0">
              {layoutPickerFormat && (
                <DDGridV1ExportLayoutPicker
                  format={layoutPickerFormat}
                  onCancel={onCancelLayoutPicker}
                  onApply={(layout) =>
                    onApplyLayout(layoutPickerFormat, layout)
                  }
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

const DDGridV1TabPage: React.FC<GridTabProps> = ({ dealId, runId }) => {
  const { t } = useTranslation("ddGrid");
  const { projectRoles } = useAuth();

  // Sprint 6.x: DD Grid uses dedicated Output Locale axis, independent from UI locale.
  // The lawyer selects Results Language in DDGridV1ViewSettings dropdown; it is
  // persisted in useDDGridV1UIStore.outputLocale and drives all backend queries.
  const outputLocale = useDDGridV1UIStore((state) => state.outputLocale);
  const presentationLocale = outputLocale;

  const projectRole = projectRoles[dealId] ?? null;

  const canRequestResultPresentations =
    projectRole === "admin" || projectRole === "editor";

  const [reviewSelection, setReviewSelection] = React.useState<
    ReviewSelectionItem[]
  >([]);
  const [isExportPanelOpen, setIsExportPanelOpen] = React.useState(false);

  // gridMode теперь читается из zustand store (format)
  const format = useDDGridV1UIStore((state) => state.format);
  const isMobile = useIsMobile();
  const gridMode: GridMode =
    isMobile ? "list" : format === "list" ? "list" : "matrix";

  // checksScope из store — используется для фильтрации в list mode
  const checksScope = useDDGridV1UIStore((state) => state.checksScope);

  // showPassInList из store — persistent между сессиями,
  // позволяет управлять фильтром извне (например, из Overview widgets)
  const showPassInList = useDDGridV1UIStore((state) => state.showPassInList);
  const setShowPassInList = useDDGridV1UIStore(
    (state) => state.setShowPassInList,
  );

  // Inline layout picker для matrix PDF/Word.
  // null — picker скрыт; "pdf" / "docx" — picker показан для этого формата.
  const [layoutPickerFormat, setLayoutPickerFormat] = React.useState<
    "pdf" | "docx" | null
  >(null);

  // Applied extra columns — то, что реально отображается в таблице.
  const [appliedExtraColumnIds, setAppliedExtraColumnIds] = React.useState<
    readonly string[]
  >([]);

  // Draft — то, что юрист сейчас выбирает в панели.
  const [draftExtraColumnIds, setDraftExtraColumnIds] = React.useState<
    readonly string[]
  >([]);

  // Открыта ли inline-панель выбора колонок.
  const [isExtraColumnsPanelOpen, setIsExtraColumnsPanelOpen] =
    React.useState<boolean>(false);
  const [gridSelectionResetToken, setGridSelectionResetToken] =
    React.useState<number>(0);
  const [viewerState, setViewerState] = React.useState<ViewerState>(null);
  const [isViewerLoading, setIsViewerLoading] = React.useState(false);
  const [viewerError, setViewerError] = React.useState<string | null>(null);

  const {
    data: ddGridV1Response,
    isLoading: isV1Loading,
    error: v1Error,
  } = useDealReviewDdGridV1(
    dealId,
    runId,
    presentationLocale,
  );

  const { data: run, error: runError } = useRun(runId, false);

  // V1 derived model
  const v1Model = React.useMemo(
    () => selectDDGridV1DerivedModel(ddGridV1Response ?? null),
    [ddGridV1Response],
  );

  // V1 QC хелперы работают напрямую с v1Model — без адаптера
  // legacyAdapter и reviewGrid.qc больше не используются

  // Компактный список visibleCheckIds для V1 List (аналогично тому,
  // что делает DDGridV1TypedGroups для matrix)
  const listVisibleCheckIds = React.useMemo<string[] | undefined>(() => {
    if (checksScope === "all") return undefined;

    const globalIds = new Set<string>();
    const docTypeIds = new Set<string>();

    for (const group of v1Model.globalGroups) {
      for (const check of group.checks) {
        globalIds.add(check.checkId);
      }
    }
    for (const cls of v1Model.docTypeClasses) {
      for (const t of cls.types) {
        for (const check of t.checks) {
          docTypeIds.add(check.checkId);
        }
      }
    }

    if (checksScope === "global_only") {
      return Array.from(globalIds);
    }
    if (checksScope === "doc_type_only") {
      // doc_type_only = все doc-type checks, кроме тех, что также
      // помечены как global (при пересечении global выигрывает)
      const result: string[] = [];
      for (const id of docTypeIds) {
        if (!globalIds.has(id)) result.push(id);
      }
      return result;
    }
    return undefined;
  }, [checksScope, v1Model]);

  // visibleListCellKeys больше не нужен — новый V1 List читает данные
  // напрямую из V1 модели и фильтрует по visibleCheckIds.

  const selectedV1Drawers = React.useMemo(
    () => getSelectedV1Drawers(v1Model, reviewSelection),
    [v1Model, reviewSelection],
  );

  const reviewQcCapability = React.useMemo(
    () => getV1QcCapability(reviewSelection, selectedV1Drawers, runId, t),
    [reviewSelection, selectedV1Drawers, runId, t],
  );

  const reviewQcDisabledNote = React.useMemo(
    () => getV1QcDisabledNote(reviewQcCapability),
    [reviewQcCapability],
  );

  const checksModeLabel = humanChecksMode(run?.checks_mode, t);

  const resetReviewSelection = React.useCallback(() => {
    setReviewSelection([]);
    setGridSelectionResetToken((prev) => prev + 1);
  }, []);

  const handleReviewSelectionChange = React.useCallback(
    (selection: ReviewSelectionItem[]) => {
      setReviewSelection(selection);
    },
    [],
  );

  const handleCloseViewer = React.useCallback(() => {
    // Освобождаем blob URL чтобы не было memory leak
    if (viewerState?.pdfUrl && viewerState.pdfUrl.startsWith("blob:")) {
      URL.revokeObjectURL(viewerState.pdfUrl);
    }
    setViewerState(null);
  }, [viewerState]);

  const didInitGridModeResetRef = React.useRef(false);

  React.useEffect(() => {
    if (!didInitGridModeResetRef.current) {
      didInitGridModeResetRef.current = true;
      return;
    }

    resetReviewSelection();
    setAppliedExtraColumnIds([]);
    setDraftExtraColumnIds([]);
    setIsExtraColumnsPanelOpen(false);
    setLayoutPickerFormat(null);
  }, [gridMode, resetReviewSelection]);

  const handleToggleExportPanel = React.useCallback(() => {
    setIsExportPanelOpen((prev) => {
      if (prev) {
        // При закрытии панели сбрасываем layout picker
        setLayoutPickerFormat(null);
      }
      return !prev;
    });
  }, []);

  const handleApplyMatrixLayout = React.useCallback(
    async (
      format: "pdf" | "docx",
      layout: DDGridV1MatrixLayout,
    ) => {
      const fileOpts = { dealName: dealId, runId: runId ?? undefined };

      if (layout === "single") {
        const matrixTable = buildDDGridV1MatrixExportTable({
          model: v1Model,
          t, // 🌟 Передаём функцию перевода
        });
        if (format === "pdf") {
          await exportMatrixSingleToPdf(matrixTable, fileOpts);
        } else {
          await exportMatrixSingleToWord(matrixTable, fileOpts);
        }
      } else if (layout === "byDocument") {
        const sectioned = buildDDGridV1DocumentSectionedExportTable({
          model: v1Model,
          t, // 🌟 Передаём функцию перевода
        });
        const sectionOpts = {
          ...fileOpts,
          titleSuffix: t("v1Tab.export.byDocumentSuffix"),
          layoutSuffix: "by_document",
        };
        if (format === "pdf") {
          await exportSectionedToPdf(sectioned, sectionOpts);
        } else {
          await exportSectionedToWord(sectioned, sectionOpts);
        }
      } else {
        // byScopeGroup
        const sectioned = buildDDGridV1ScopeGroupSectionedExportTable({
          model: v1Model,
          t, // 🌟 Передаём функцию перевода
        });
        const sectionOpts = {
          ...fileOpts,
          titleSuffix: t("v1Tab.export.byScopeSuffix"),
          layoutSuffix: "by_scope",
        };
        if (format === "pdf") {
          await exportSectionedToPdf(sectioned, sectionOpts);
        } else {
          await exportSectionedToWord(sectioned, sectionOpts);
        }
      }

      // Скрыть picker после успешного экспорта
      setLayoutPickerFormat(null);
    },
    [dealId, runId, v1Model, t],
  );

  const openViewerAt: OpenViewerAtFn = React.useCallback(async (loc) => {
    try {
      setViewerError(null);
      setIsViewerLoading(true);

      // Получаем PDF через streaming endpoint — backend читает из приватного
      // MinIO и отдаёт браузеру напрямую. Никаких presigned URL.
      const pdfResponse = await client.get(
        `/api/v1/documents/${loc.documentId}/converted-pdf-content`,
        { responseType: "blob" },
      );

      const pdfBlob = pdfResponse.data as Blob;
      const pdfUrl = URL.createObjectURL(pdfBlob);

      // layout и chunks запрашиваем параллельно, каждый в try/catch:
      // если endpoint вернул ошибку — viewer откроется без overlay hints.
      const [layoutJson, chunksJson] = await Promise.all([
        client
          .get<unknown>(`/api/v1/documents/${loc.documentId}/layout-for-viewer`)
          .then((r) => r.data)
          .catch(() => undefined),
        client
          .get<unknown>(`/api/v1/documents/${loc.documentId}/sized-chunks`)
          .then((r) => r.data)
          .catch(() => undefined),
      ]);

      setViewerState({
        location: loc,
        pdfUrl,
        layoutElements: parseLayoutElements(layoutJson),
        sizedChunks: parseSizedChunks(chunksJson),
      });
    } catch (error: unknown) {
      // NOTE: getErrorMessage is a pure helper; t() is not available inside
      // this callback without stale closure, so we build the string via
      // the i18n instance directly.  However, since this is a callback
      // created with useCallback and we need `t`, we add `t` to deps below.
      setViewerError(
        t("v1Tab.viewer.loadError", { error: getErrorMessage(error) }),
      );
    } finally {
      setIsViewerLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  if (!runId) {
    return (
      <StatusStateCard
        title={t("v1Tab.noRunTitle")}
        description={t("v1Tab.noRunDescription")}
      />
    );
  }

  if (isV1Loading) {
    return <StatusStateCard title={t("v1Tab.loadingTitle")} />;
  }

  if (v1Error) {
    return (
      <StatusStateCard
        title={t("v1Tab.errorTitle")}
        tone="error"
      />
    );
  }

  const matrixSectionTitle =
    gridMode === "matrix"
      ? t("v1Tab.matrixTitle")
      : t("v1Tab.listTitle");

  const matrixSectionSubtitle =
    gridMode === "matrix"
      ? t("v1Tab.matrixSubtitle")
      : t("v1Tab.listSubtitle");

  return (
    <div className="flex flex-col gap-4 lg:h-full lg:min-h-0 lg:overflow-hidden">
      {/* Warning об отсутствии run metadata — если есть, показываем над секцией */}
      {runError ? (
        <div className="shrink-0">
          <RunMetaWarning visible={true} />
        </div>
      ) : null}

      {/* ── Grid section.
          Desktop: flex-1 + min-h-0 → AG Grid скроллится внутри.
          Mobile: натуральная высота → таблица растёт по всем строкам,
          скроллится страница целиком. */}
      <section className="flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm lg:min-h-0 lg:flex-1">
        {/* Toolbar — shrink-0 */}
        <div className="shrink-0">
          <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                {matrixSectionTitle}
              </h2>
              {gridMode === "matrix" ? (
                <DDGridV1SummaryLine
                  documentsCount={v1Model.stats.documentsCount}
                  checksCount={v1Model.stats.checksCount}
                  findingsCount={selectedV1Drawers.length}
                  runtimeColsCount={v1Model.stats.runtimeColumnsCount}
                  definedCellsCount={v1Model.stats.definedCellsCount}
                  notDefinedCellsCount={v1Model.stats.notDefinedCellsCount}
                  errorCellsCount={v1Model.stats.errorCellsCount}
                  checksMode={checksModeLabel ?? null}
                  className="mt-0.5 text-[11px] text-[var(--text-muted)]"
                />
              ) : (
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                  {matrixSectionSubtitle}
                </p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {runId ? (
                <ResultPresentationStatus
                  dealId={dealId}
                  runId={runId}
                  presentationLocale={presentationLocale}
                  canRequest={canRequestResultPresentations}
                />
              ) : null}
            </div>
          </div>

          <div className="px-5 pb-3">
            {/* Настройки отображения + кнопки действий.
                Desktop: горизонтальный layout — settings слева, кнопки справа.
                Mobile: вертикальный стек — settings сверху (info-баннер +
                сегменты на всю ширину), кнопки под ними в один ряд с wrap. */}
            <div className="mb-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between">
                <div className="min-w-0 lg:flex-1">
                  <DDGridV1ViewSettings
                    hideFormatToggle={isMobile}
                    stretch={isMobile}
                  />
                </div>

                <div className="flex flex-col gap-1.5 lg:shrink-0">
                  {/* Невидимый лейбл с теми же классами, что и слева.
                      Занимает идентичное вертикальное пространство для идеального выравнивания без магических чисел. */}
                  <span
                    className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)] invisible"
                    aria-hidden="true"
                  >
                    {t("v1Tab.actionsLabel")}
                  </span>

                  <div className="flex flex-wrap items-center gap-2">
                    {gridMode === "list" && (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          variant={!showPassInList ? "outline" : "secondary"}
                          onClick={() => setShowPassInList(!showPassInList)}
                          title={
                            showPassInList
                              ? t("v1Tab.hidePassTitle")
                              : t("v1Tab.showPassTitle")
                          }
                          aria-pressed={!showPassInList}
                          className={!showPassInList ? INLINE_PANEL_ACTIVE_CLASS : ""}
                        >
                          {showPassInList
                            ? t("v1Tab.hidePass")
                            : t("v1Tab.showPass")}
                        </Button>

                        <Button
                          type="button"
                          size="sm"
                          variant={isExtraColumnsPanelOpen ? "outline" : "secondary"}
                          onClick={() => {
                            if (!isExtraColumnsPanelOpen) {
                              setDraftExtraColumnIds(appliedExtraColumnIds);
                            }
                            setIsExtraColumnsPanelOpen((prev) => !prev);
                          }}
                          title={t("v1Tab.extraColumnsTitle")}
                          aria-expanded={isExtraColumnsPanelOpen}
                          aria-controls="dd-grid-v1-extra-columns-panel"
                          leftIcon={<SlidersHorizontal className="h-4 w-4" />}
                          rightIcon={
                            <ChevronRight
                              className={`h-4 w-4 transition-transform duration-200 ${
                                isExtraColumnsPanelOpen ? "rotate-90" : "rotate-0"
                              }`}
                            />
                          }
                          className={
                            isExtraColumnsPanelOpen ? INLINE_PANEL_ACTIVE_CLASS : ""
                          }
                        >
                          {t("v1Tab.extraColumnsButton")}
                          {appliedExtraColumnIds.length > 0
                            ? ` (${appliedExtraColumnIds.length})`
                            : ""}
                        </Button>
                      </>
                    )}

                    <Button
                      type="button"
                      size="sm"
                      variant={isExportPanelOpen ? "outline" : "secondary"}
                      onClick={handleToggleExportPanel}
                      title={t("v1Tab.exportTitle")}
                      aria-expanded={isExportPanelOpen}
                      aria-controls="dd-grid-v1-export-panel"
                      leftIcon={<Download className="h-4 w-4" />}
                      rightIcon={
                        <ChevronRight
                          className={`h-4 w-4 transition-transform duration-200 ${
                            isExportPanelOpen ? "rotate-90" : "rotate-0"
                          }`}
                        />
                      }
                      className={isExportPanelOpen ? INLINE_PANEL_ACTIVE_CLASS : ""}
                    >
                      {t("v1Tab.exportButton")}
                    </Button>
                  </div>
                </div>
              </div>
            </div>

            <ExportPanel
              open={isExportPanelOpen}
              model={v1Model}
              mode={gridMode}
              visibleCheckIds={
                gridMode === "list" ? listVisibleCheckIds : undefined
              }
              includePassResults={gridMode === "list" ? showPassInList : true}
              visibleExtraColumnIds={
                gridMode === "list" ? appliedExtraColumnIds : undefined
              }
              dealName={dealId}
              runId={runId ?? undefined}
              layoutPickerFormat={layoutPickerFormat}
              onRequestLayoutPicker={setLayoutPickerFormat}
              onCancelLayoutPicker={() => setLayoutPickerFormat(null)}
              onApplyLayout={handleApplyMatrixLayout}
            />

            {/* Inline-панель выбора дополнительных колонок */}
            <div
              id="dd-grid-v1-extra-columns-panel"
              aria-hidden={!isExtraColumnsPanelOpen}
              className={`grid overflow-hidden transition-[grid-template-rows,opacity,margin] duration-300 ease-out ${
                isExtraColumnsPanelOpen
                  ? "mt-3 grid-rows-[1fr] opacity-100"
                  : "mt-0 grid-rows-[0fr] opacity-0"
              }`}
            >
              <div className="min-h-0">
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        {t("v1Tab.extraColumnsPanel.title")}
                      </p>
                      <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                        {t("v1Tab.extraColumnsPanel.description")}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setDraftExtraColumnIds(appliedExtraColumnIds);
                          setIsExtraColumnsPanelOpen(false);
                        }}
                      >
                        {t("v1Tab.extraColumnsPanel.cancel")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="primary"
                        leftIcon={<Check className="h-4 w-4" />}
                        onClick={() => {
                          setAppliedExtraColumnIds(draftExtraColumnIds);
                          setIsExtraColumnsPanelOpen(false);
                        }}
                      >
                        {t("v1Tab.extraColumnsPanel.apply")}
                      </Button>
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                    {DD_GRID_V1_EXTRA_COLUMNS.map((col) => {
                      const isChecked = draftExtraColumnIds.includes(col.id);
                      return (
                        <label
                          key={col.id}
                          className="flex cursor-pointer items-start gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-xs transition-colors hover:bg-[var(--bg-card-hover)]"
                          title={col.description}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setDraftExtraColumnIds((prev) =>
                                  prev.includes(col.id)
                                    ? prev
                                    : [...prev, col.id],
                                );
                              } else {
                                setDraftExtraColumnIds((prev) =>
                                  prev.filter((id) => id !== col.id),
                                );
                              }
                            }}
                            className="mt-0.5 h-3.5 w-3.5 shrink-0 cursor-pointer rounded border-[var(--border)] text-[var(--accent-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]"
                          />
                          <div className="min-w-0">
                            <div className="font-medium text-[var(--text-primary)]">
                              {col.label}
                            </div>
                            <div className="mt-0.5 line-clamp-2 text-[10px] leading-4 text-[var(--text-muted)]">
                              {col.description}
                            </div>
                          </div>
                        </label>
                      );
                    })}
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--border-subtle)] pt-2">
                    <button
                      type="button"
                      onClick={() =>
                        setDraftExtraColumnIds(
                          DD_GRID_V1_EXTRA_COLUMNS.map((c) => c.id),
                        )
                      }
                      className="text-[10px] font-medium text-[var(--accent-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]"
                    >
                      {t("v1Tab.extraColumnsPanel.selectAll")}
                    </button>
                    <span className="text-[10px] text-[var(--text-faint)]">·</span>
                    <button
                      type="button"
                      onClick={() => setDraftExtraColumnIds([])}
                      className="text-[10px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]"
                    >
                      {t("v1Tab.extraColumnsPanel.deselectAll")}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {reviewQcCapability.supported && runId ? (
              <div className="mt-4">
                <div className="mb-2 flex items-center gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("v1Tab.qc.heading")}
                  </h3>
                  <span className="text-[10px] text-[var(--text-faint)]">
                    {t("v1Tab.qc.hint")}
                  </span>
                </div>
                <DDGridV1QcBulkActions
                  selectedRowsCount={reviewQcCapability.selectedRowsCount}
                  selectedFindingsCount={reviewQcCapability.selectedFindingsCount}
                  selectedDrawers={selectedV1Drawers}
                  runId={runId}
                  capability={reviewQcCapability}
                />
              </div>
            ) : reviewQcDisabledNote ? (
              <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3 text-sm text-[var(--text-secondary)]">
                {reviewQcDisabledNote}
              </div>
            ) : null}

            <div className="mt-4 border-t border-[var(--border-subtle)]" />
          </div>
        </div>

        {/* Grid viewport.
            Desktop: flex-1 + overflow-hidden → AG Grid scroll внутри.
            Mobile: натуральная высота → таблица занимает столько, сколько
            нужно, скроллится страница целиком. */}
        <div className="relative px-5 py-5 lg:min-h-0 lg:flex-1 lg:overflow-hidden">
          {gridMode === "matrix" ? (
            <DDGridV1TypedGroups
              runId={runId}
              model={v1Model}
              rows={v1Model.rows}
              columns={[]}
              onOpenAtLocation={openViewerAt}
              onSelectionChange={handleReviewSelectionChange}
              clearSelectionToken={gridSelectionResetToken}
            />
          ) : (
            <DDGridV1List
              key={`review-list-v1:${gridSelectionResetToken}`}
              runId={runId}
              model={v1Model}
              rows={v1Model.rows}
              columns={[]}
              visibleCheckIds={listVisibleCheckIds}
              includePassResults={showPassInList}
              visibleExtraColumnIds={appliedExtraColumnIds}
              onOpenAtLocation={openViewerAt}
              onSelectionChange={handleReviewSelectionChange}
              clearSelectionToken={gridSelectionResetToken}
            />
          )}
        </div>
      </section>

      <DocumentViewerModal
        // B7.9.2: reset viewer state on location change by remounting.
        // This is the idiomatic alternative to syncing visiblePage
        // via useEffect (which would trigger react-hooks/set-state-in-effect).
        key={
          viewerState
            ? `viewer-${
                viewerState.location?.clauseUid ??
                viewerState.location?.page ??
                viewerState.location?.chunkId ??
                "default"
              }`
            : "viewer-closed"
        }
        open={Boolean(viewerState)}
        onClose={handleCloseViewer}
        fileUrl={viewerState?.pdfUrl ?? null}
        location={viewerState?.location ?? null}
        title={
          viewerError ??
          (isViewerLoading ? t("v1Tab.viewer.loadingPdf") : null)
        }
        layoutElements={viewerState?.layoutElements}
        sizedChunks={viewerState?.sizedChunks}
      />
    </div>
  );
};

export default DDGridV1TabPage;

