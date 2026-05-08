// =============================================================
// src/pages/tabs/ReportTab.tsx
// Вкладка «Отчёт»:
// - запуск экспорта (Excel/Word)
// - отслеживание статуса
// - скачивание готового файла
// - отображение backend error_message для failed export
// - приведено к единому стилю Overview / PageSection
// - кнопки переведены на общий ui/Button
// =============================================================

import React, { useMemo, useState } from "react";
import { useLatestRun } from "../../api/results";
import { useRequestExport, useExportStatus } from "../../api/exports";
import type { ExportType } from "../../types/exports";
import { EXPORT_TYPE_LABEL } from "../../constants";

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
  dealId: string;
}

function formatFileSizeKb(bytes?: number | null): string | null {
  if (typeof bytes !== "number" || Number.isNaN(bytes) || bytes <= 0) {
    return null;
  }

  return `${Math.round(bytes / 1024)} КБ`;
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
          Генерировать
        </Button>
      </div>
    </div>
  );
}

export const ReportTab: React.FC<Props> = ({ dealId }) => {
  const { data: latestRun } = useLatestRun(dealId);
  const requestExport = useRequestExport();

  const [activeExportId, setActiveExportId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const {
    data: exportData,
    error: exportStatusError,
    isFetching: isFetchingExportStatus,
  } = useExportStatus(activeExportId);

  const isRunExportable =
    !!latestRun &&
    (latestRun.status === "completed" ||
      latestRun.status === "completed_with_errors");

  const isGenerating = requestExport.isPending;

  const statusErrorMessage = useMemo(() => {
    const err = exportStatusError as any;
    return err?.response?.data?.detail || err?.message || null;
  }, [exportStatusError]);

  const exportTitle =
    exportData?.export_type
      ? EXPORT_TYPE_LABEL[exportData.export_type] || exportData.export_type
      : null;

  const exportFailedMessage =
    (typeof exportData?.error_message === "string" &&
      exportData.error_message.trim()) ||
    "Экспорт завершился ошибкой. Попробуйте ещё раз или проверьте backend-логи.";

  const completedFileSizeLabel = formatFileSizeKb(exportData?.file_size_bytes);

  const handleGenerate = async (exportType: ExportType) => {
    setLastError(null);

    if (!latestRun?.id) {
      setLastError(
        "Анализ не завершён. Запустите анализ на вкладке «Обзор».",
      );
      return;
    }

    if (!isRunExportable) {
      setLastError(
        "Экспорт доступен только после завершения анализа (completed или completed_with_errors).",
      );
      return;
    }

    if (isGenerating) {
      return;
    }

    try {
      const exp = await requestExport.mutateAsync({
        runId: latestRun.id,
        exportType,
      });

      setActiveExportId(exp.id);
    } catch (error: any) {
      const detail =
        error?.response?.data?.detail ||
        error?.message ||
        "Ошибка запроса экспорта";

      console.error("Export request failed:", error?.response?.status);
      console.error("Export response data:", error?.response?.data);

      setLastError(
        typeof detail === "string" ? detail : "Ошибка запроса экспорта",
      );
    }
  };

  const handleDownload = () => {
    if (!exportData || exportData.status !== "completed") return;
    if (!exportData.download_url) return;

    window.open(exportData.download_url, "_blank", "noopener,noreferrer");
  };

  if (!latestRun || !isRunExportable) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 text-center shadow-sm">
        <div className="flex min-h-[360px] flex-col items-center justify-center">
          <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
            <FileText size={26} className="text-[var(--text-muted)]" />
          </div>

          <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
            Отчёт будет доступен после завершения анализа
          </h2>

          <p className="max-w-md text-[12px] leading-5 text-[var(--text-secondary)]">
            Экспорт доступен только для последнего run со статусом{" "}
            <span className="font-medium">completed</span> или{" "}
            <span className="font-medium">completed_with_errors</span>. Запустите
            анализ и дождитесь его завершения.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageSection
        title="Отчёт"
        subtitle="Выберите формат и запустите генерацию. Отчёт будет сформирован по последнему завершённому анализу."
      >
        <div className="space-y-4">
          {lastError ? <InlineAlert tone="error" message={lastError} /> : null}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <ExportCard
              title="DD Grid"
              description="Полная таблица результатов проверок с цветовым кодированием severity."
              icon={<FileSpreadsheet size={22} className="text-emerald-500" />}
              format="Excel (.xlsx)"
              onGenerate={() => handleGenerate("grid_xlsx")}
              isGenerating={isGenerating}
            />

            <ExportCard
              title="Deal Summary"
              description="KPI, Top Risks, разбивка по типам документов и список запросов."
              icon={<FileSpreadsheet size={22} className="text-sky-500" />}
              format="Excel (.xlsx)"
              onGenerate={() => handleGenerate("deal_summary_xlsx")}
              isGenerating={isGenerating}
            />

            <ExportCard
              title="Отчёт DD"
              description="Executive Summary, критические находки, качество анализа, запросы."
              icon={<FileText size={22} className="text-indigo-500" />}
              format="Word (.docx)"
              onGenerate={() => handleGenerate("report_docx")}
              isGenerating={isGenerating}
            />
          </div>
        </div>
      </PageSection>

      {activeExportId && (
        <PageSection
          title="Статус экспорта"
          subtitle="Следите за генерацией и скачайте готовый файл после завершения."
          rightSlot={
            isFetchingExportStatus ? (
              <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
                <RefreshCw size={14} className="animate-spin" />
                <span>Обновляем статус…</span>
              </div>
            ) : null
          }
        >
          {statusErrorMessage ? (
            <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700">
              <AlertCircle size={20} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="text-sm font-medium">
                  Не удалось получить статус экспорта
                </div>
                <div className="text-xs leading-5">{statusErrorMessage}</div>
              </div>
            </div>
          ) : !exportData ||
            exportData.status === "processing" ||
            exportData.status === "pending" ? (
            <div className="flex items-center gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3 text-[var(--accent)]">
              <Loader2 className="animate-spin" size={18} />
              <span className="text-xs">
                Генерируем файл… Обычно это занимает 10–30 секунд.
              </span>
            </div>
          ) : exportData.status === "completed" ? (
            <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
              <div className="flex flex-wrap items-center gap-3 text-emerald-700">
                <CheckCircle size={20} />
                <span className="text-sm font-medium">
                  {exportTitle || "Файл"} готов к скачиванию
                </span>
                {completedFileSizeLabel && (
                  <span className="text-[11px] text-emerald-900/70">
                    ({completedFileSizeLabel})
                  </span>
                )}
              </div>

              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={handleDownload}
                disabled={!exportData.download_url}
                leftIcon={<Download size={14} />}
              >
                Скачать файл
              </Button>
            </div>
          ) : exportData.status === "failed" ? (
            <div className="space-y-3">
              <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700">
                <AlertCircle size={20} className="mt-0.5 shrink-0" />
                <div className="space-y-1">
                  <div className="text-sm font-medium">
                    {exportTitle
                      ? `${exportTitle}: ошибка генерации`
                      : "Ошибка генерации экспорта"}
                  </div>
                  <div className="text-xs leading-5">{exportFailedMessage}</div>
                </div>
              </div>

              <p className="text-[11px] text-[var(--text-muted)]">
                После устранения причины ошибки можно повторно запустить
                генерацию этого формата отчёта.
              </p>
            </div>
          ) : (
            <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-700">
              <AlertCircle size={20} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="text-sm font-medium">
                  Неожиданный статус экспорта
                </div>
                <div className="text-xs">
                  Текущий статус:{" "}
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

