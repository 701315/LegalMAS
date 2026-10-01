// =============================================================
// src/pages/tabs/ReportTab.tsx
// =============================================================

import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useRun } from "../../api/runs";
import { useRequestExport, useExportStatus, downloadExport } from "../../api/exports";
import type { ExportType } from "../../types/exports";
import { EXPORT_TYPE_LABEL } from "../../constants";
import { useDDGridV1UIStore } from "./dd-grid-v1/ddGridV1.collapseStore";

import {
  FileText,
  Download,
  Loader2,
  CheckCircle,
  AlertCircle,
  FileSpreadsheet,
  RefreshCw,
} from "lucide-react";
import InlineAlert from "../../components/InlineAlert";
import PageSection from "../../components/ui/PageSection";
import Button from "../../components/ui/Button";

interface Props {
  runId: string | null;
}

function formatFileSizeKb(
  bytes: number | null | undefined,
  tFn: (key: string, options?: any) => string,
): string | null {
  if (typeof bytes !== "number" || Number.isNaN(bytes) || bytes <= 0) {
    return null;
  }
  return tFn("reportTab.fileSize", { count: Math.round(bytes / 1024) });
}

interface ExportCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  format: string;
  onGenerate: () => void;
  isGenerating: boolean;
}

function ExportCard({
  title,
  description,
  icon,
  format,
  onGenerate,
  isGenerating,
}: ExportCardProps) {
  const { t } = useTranslation("exports");

  return (
    <div className="card-surface card-surface-hover flex h-full flex-col justify-between p-4">
      <div className="space-y-3">
        <div className="flex items-start gap-3">
          <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
            {icon}
          </div>

          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </h3>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {format}
            </p>
          </div>
        </div>

        <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {description}
        </p>
      </div>

      <div className="mt-4">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          fullWidth
          onClick={onGenerate}
          isLoading={isGenerating}
          leftIcon={!isGenerating ? <Download size={14} /> : undefined}
        >
          {t("reportTab.cards.generate")}
        </Button>
      </div>
    </div>
  );
}

function extractErrorMessage(err: unknown): string | null {
  if (err == null) return null;

  if (typeof err === "object") {
    const maybeAxios = err as {
      response?: { data?: { detail?: unknown } };
      message?: unknown;
    };

    const detail = maybeAxios.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }

    const message = maybeAxios.message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }

  return null;
}

export const ReportTab: React.FC<Props> = ({ runId }) => {
  const { t } = useTranslation("exports");
  const { data: run } = useRun(runId);
  const requestExport = useRequestExport();

  // Shared output locale selector (Requests / DD Grid / Report tabs).
  // The chosen value drives the language of every export.
  const outputLocale = useDDGridV1UIStore((state) => state.outputLocale);

  const [activeExportId, setActiveExportId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const {
    data: exportData,
    error: exportStatusError,
    isFetching: isFetchingExportStatus,
  } = useExportStatus(activeExportId);

  const isRunExportable =
    !!run &&
    (run.status === "completed" || run.status === "completed_with_errors");

  const isGenerating = requestExport.isPending;

  const statusErrorMessage = useMemo(
    () => extractErrorMessage(exportStatusError),
    [exportStatusError],
  );

  const exportTitle =
    exportData?.export_type
      ? EXPORT_TYPE_LABEL[exportData.export_type] || exportData.export_type
      : null;

  const exportFailedMessage =
    (typeof exportData?.error_message === "string" &&
      exportData.error_message.trim()) ||
    t("reportTab.statusSection.failedFallback");

  const completedFileSizeLabel = formatFileSizeKb(exportData?.file_size_bytes, t);

  const handleGenerate = async (exportType: ExportType) => {
    setLastError(null);

    if (!run?.id) {
      setLastError(t("reportTab.errors.analysisNotFinished"));
      return;
    }

    if (!isRunExportable) {
      setLastError(t("reportTab.errors.exportUnavailable"));
      return;
    }

    if (isGenerating) {
      return;
    }

    try {
      const exp = await requestExport.mutateAsync({
        runId: run.id,
        exportType,
        outputLocale,
      });

      setActiveExportId(exp.id);
    } catch (error: unknown) {
      const detail = extractErrorMessage(error);

      console.error(
        "Export request failed:",
        (error as { response?: { status?: unknown } })?.response?.status,
      );
      console.error(
        "Export response data:",
        (error as { response?: { data?: unknown } })?.response?.data,
      );

      setLastError(detail ?? t("reportTab.errors.requestFailed"));
    }
  };

  const handleDownload = async () => {
    if (!activeExportId) return;
    if (!exportData || exportData.status !== "completed") return;

    setIsDownloading(true);
    setLastError(null);

    try {
      await downloadExport(activeExportId, exportData.export_type);
    } catch (error: unknown) {
      const detail = extractErrorMessage(error);
      console.error("Download failed:", error);
      setLastError(detail ?? t("reportTab.errors.downloadFailed"));
    } finally {
      setIsDownloading(false);
    }
  };

  if (!run || !isRunExportable) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 text-center shadow-sm">
        <div className="flex min-h-[360px] flex-col items-center justify-center">
          <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
            <FileText size={26} className="text-[var(--text-muted)]" />
          </div>

          <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
            {t("reportTab.emptyState.title")}
          </h2>

          <p className="max-w-md text-[12px] leading-5 text-[var(--text-secondary)]">
            {t("reportTab.emptyState.description")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageSection
        title={t("reportTab.pageSection.title")}
        subtitle={t("reportTab.pageSection.subtitle")}
      >
        <div className="space-y-4">
          {lastError ? (
            <InlineAlert tone="error" message={lastError} />
          ) : null}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ExportCard
              title={t("reportTab.cards.ddGrid.title")}
              description={t("reportTab.cards.ddGrid.description")}
              icon={
                <FileSpreadsheet
                  size={22}
                  className="text-[var(--color-success)]"
                />
              }
              format={t("reportTab.cards.ddGrid.format")}
              onGenerate={() => handleGenerate("grid_xlsx")}
              isGenerating={isGenerating}
            />

            <ExportCard
              title={t("reportTab.cards.dealSummary.title")}
              description={t("reportTab.cards.dealSummary.description")}
              icon={
                <FileSpreadsheet
                  size={22}
                  className="text-[var(--color-blue)]"
                />
              }
              format={t("reportTab.cards.dealSummary.format")}
              onGenerate={() => handleGenerate("deal_summary_xlsx")}
              isGenerating={isGenerating}
            />

            <ExportCard
              title={t("reportTab.cards.ddReport.title")}
              description={t("reportTab.cards.ddReport.description")}
              icon={
                <FileText
                  size={22}
                  className="text-[var(--color-purple)]"
                />
              }
              format={t("reportTab.cards.ddReport.format")}
              onGenerate={() => handleGenerate("report_docx")}
              isGenerating={isGenerating}
            />
          </div>
        </div>
      </PageSection>

      {activeExportId && (
        <PageSection
          title={t("reportTab.statusSection.title")}
          subtitle={t("reportTab.statusSection.subtitle")}
          rightSlot={
            isFetchingExportStatus ? (
              <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
                <RefreshCw size={14} className="animate-spin" />
                <span>{t("reportTab.statusSection.updating")}</span>
              </div>
            ) : null
          }
        >
          {statusErrorMessage ? (
            <div className="flex items-start gap-3 rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3 text-[var(--color-error-text)]">
              <AlertCircle size={20} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="text-sm font-medium">
                  {t("reportTab.statusSection.fetchError")}
                </div>
                <div className="text-xs leading-5">{statusErrorMessage}</div>
              </div>
            </div>
          ) : !exportData ||
            exportData.status === "processing" ||
            exportData.status === "pending" ? (
            <div className="flex items-center gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3 text-[var(--accent-primary)]">
              <Loader2 className="animate-spin" size={18} />
              <span className="text-xs">
                {t("reportTab.statusSection.generating")}
              </span>
            </div>
          ) : exportData.status === "completed" ? (
            <div className="space-y-3 rounded-xl border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-4 py-3">
              <div className="flex flex-wrap items-center gap-3 text-[var(--color-success-text)]">
                <CheckCircle size={20} />
                <span className="text-sm font-medium">
                  {exportTitle
                    ? t("reportTab.statusSection.ready", { title: exportTitle })
                    : t("reportTab.statusSection.readyFallback")}
                </span>
                {completedFileSizeLabel && (
                  <span className="text-[11px] text-[var(--color-success-text)] opacity-70">
                    ({completedFileSizeLabel})
                  </span>
                )}
              </div>

              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={handleDownload}
                disabled={!exportData.download_url || isDownloading}
                isLoading={isDownloading}
                leftIcon={!isDownloading ? <Download size={14} /> : undefined}
              >
                {isDownloading ? t("reportTab.statusSection.downloading") : t("reportTab.statusSection.downloadBtn")}
              </Button>
            </div>
          ) : exportData.status === "failed" ? (
            <div className="space-y-3">
              <div className="flex items-start gap-3 rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3 text-[var(--color-error-text)]">
                <AlertCircle size={20} className="mt-0.5 shrink-0" />
                <div className="space-y-1">
                  <div className="text-sm font-medium">
                    {exportTitle
                      ? t("reportTab.statusSection.failedWithTitle", { title: exportTitle })
                      : t("reportTab.statusSection.failed")}
                  </div>
                  <div className="text-xs leading-5">
                    {exportFailedMessage}
                  </div>
                </div>
              </div>

              <p className="text-[11px] text-[var(--text-muted)]">
                {t("reportTab.statusSection.failedHint")}
              </p>
            </div>
          ) : (
            <div className="flex items-start gap-3 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3 text-[var(--color-warning-text)]">
              <AlertCircle size={20} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="text-sm font-medium">
                  {t("reportTab.statusSection.unexpectedStatus")}
                </div>
                <div className="text-xs">
                  {t("reportTab.statusSection.currentStatus")}
                  <span className="font-semibold">{exportData.status}</span>
                </div>
              </div>
            </div>
          )}
        </PageSection>
      )}
    </div>
  );
};

export default ReportTab;


