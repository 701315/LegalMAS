// =============================================================
// src/pages/tabs/ReportTab.tsx
// Вкладка «Отчёт»:
// - запуск экспорта (Excel/Word)
// - отслеживание статуса
// - скачивание готового файла
// - отображение backend error_message для failed export
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

interface Props {
  dealId: string;
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
      <div className="flex min-h-[360px] flex-col items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 text-center">
        <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
          <FileText size={26} className="text-[var(--text-muted)]" />
        </div>
        <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
          Отчёт будет доступен после завершения анализа
        </h2>
        <p className="max-w-md text-[11px] text-[var(--text-secondary)]">
          Экспорт доступен только для последнего run со статусом{" "}
          <span className="font-medium">completed</span> или{" "}
          <span className="font-medium">completed_with_errors</span>. Запустите
          анализ и дождитесь его завершения.
        </p>
      </div>
    );
  }

  const renderChecksModeLabel = () => {
    const mode = latestRun.checks_mode;
    if (!mode) return null;
    if (mode === "global_and_doc_type") return "Плейбук + типы документов";
    if (mode === "global_only") return "Только плейбук";
    if (mode === "doc_type_only") return "Только типы документов";
    return mode;
  };

  const exportTitle =
    exportData?.export_type
      ? EXPORT_TYPE_LABEL[exportData.export_type] || exportData.export_type
      : null;

  const exportFailedMessage =
    (typeof exportData?.error_message === "string" &&
      exportData.error_message.trim()) ||
    "Экспорт завершился ошибкой. Попробуйте ещё раз или проверьте backend-логи.";

  return (
    <div className="space-y-6">
      <PageSection
        title="Отчёт"
        subtitle="Выберите формат и запустите генерацию. Отчёт будет сформирован по последнему завершённому анализу."
      >
        <div className="space-y-1 text-[11px] text-[var(--text-muted)]">
          <p>
            Анализ: run{" "}
            <span className="font-mono text-[var(--text-secondary)]">
              {latestRun.id}
            </span>{" "}
            · статус:{" "}
            <span className="font-medium text-[var(--text-secondary)]">
              {latestRun.status}
            </span>
          </p>

          {latestRun.profile && (
            <p>
              Профиль анализа:{" "}
              <span className="font-medium text-[var(--text-secondary)]">
                {latestRun.profile}
              </span>
            </p>
          )}

          {renderChecksModeLabel() && (
            <p>
              Режим проверок:{" "}
              <span className="font-medium text-[var(--text-secondary)]">
                {renderChecksModeLabel()}
              </span>
            </p>
          )}

          {latestRun.pipeline_strategy && (
            <p>
              Стратегия пайплайна:{" "}
              <span className="font-medium text-[var(--text-secondary)]">
                {latestRun.pipeline_strategy}
              </span>
            </p>
          )}
        </div>

        <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
          Отчёты, сформированные ниже, будут использовать последний завершённый
          анализ
          {renderChecksModeLabel() || latestRun.pipeline_strategy ? ": " : "."}
          {renderChecksModeLabel() && (
            <>
              {" "}
              режим проверок{" "}
              <span className="font-medium text-[var(--text-primary)]">
                {renderChecksModeLabel()}
              </span>
            </>
          )}
          {latestRun.pipeline_strategy && (
            <>
              {renderChecksModeLabel() && " · "}
              стратегия пайплайна{" "}
              <span className="font-medium text-[var(--text-primary)]">
                {latestRun.pipeline_strategy}
              </span>
            </>
          )}
        </div>

        {lastError && <InlineAlert tone="error" message={lastError} />}

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <ExportCard
            title="DD Grid"
            description="Полная таблица результатов проверок с цветовым кодированием severity."
            icon={<FileSpreadsheet size={24} className="text-emerald-500" />}
            format="Excel (.xlsx)"
            onGenerate={() => handleGenerate("grid_xlsx")}
            isGenerating={isGenerating}
          />

          <ExportCard
            title="Deal Summary"
            description="KPI, Top Risks, разбивка по типам документов и список запросов."
            icon={<FileSpreadsheet size={24} className="text-sky-500" />}
            format="Excel (.xlsx)"
            onGenerate={() => handleGenerate("deal_summary_xlsx")}
            isGenerating={isGenerating}
          />

          <ExportCard
            title="Отчёт DD"
            description="Executive Summary, критические находки, качество анализа, запросы."
            icon={<FileText size={24} className="text-indigo-500" />}
            format="Word (.docx)"
            onGenerate={() => handleGenerate("report_docx")}
            isGenerating={isGenerating}
          />
        </div>
      </PageSection>

      {activeExportId && (
        <PageSection
          title="Статус экспорта"
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
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
              <AlertCircle size={20} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="text-sm font-medium">
                  Не удалось получить статус экспорта
                </div>
                <div className="text-xs">{statusErrorMessage}</div>
              </div>
            </div>
          ) : !exportData ||
            exportData.status === "processing" ||
            exportData.status === "pending" ? (
            <div className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3 text-[var(--accent)]">
              <Loader2 className="animate-spin" size={18} />
              <span className="text-xs">
                Генерируем файл… Обычно это занимает 10–30 секунд.
              </span>
            </div>
          ) : exportData.status === "completed" ? (
            <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
              <div className="flex flex-wrap items-center gap-3 text-emerald-700">
                <CheckCircle size={20} />
                <span className="text-sm font-medium">
                  {exportTitle || "Файл"} готов к скачиванию
                </span>
                {typeof exportData.file_size_bytes === "number" && (
                  <span className="text-[11px] text-emerald-900/70">
                    ({Math.round(exportData.file_size_bytes / 1024)} КБ)
                  </span>
                )}
              </div>

              <button
                type="button"
                onClick={handleDownload}
                disabled={!exportData.download_url}
                className="mt-2 inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Download size={14} />
                Скачать файл
              </button>
            </div>
          ) : exportData.status === "failed" ? (
            <div className="space-y-3">
              <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
                <AlertCircle size={20} className="mt-0.5 shrink-0" />
                <div className="space-y-1">
                  <div className="text-sm font-medium">
                    {exportTitle
                      ? `${exportTitle}: ошибка генерации`
                      : "Ошибка генерации экспорта"}
                  </div>
                  <div className="text-xs">{exportFailedMessage}</div>
                </div>
              </div>

              <p className="text-[11px] text-[var(--text-muted)]">
                После устранения причины ошибки можно повторно запустить
                генерацию этого формата отчёта.
              </p>
            </div>
          ) : (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-amber-700">
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
    <div className="flex h-full flex-col justify-between rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 text-xs transition hover:border-[var(--accent)] hover:shadow-md">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
            {icon}
          </div>
          <div>
            <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">
              {title}
            </h4>
            <p className="text-[11px] text-[var(--text-muted)]">{format}</p>
          </div>
        </div>

        <p className="text-[11px] text-[var(--text-secondary)]">
          {description}
        </p>
      </div>

      <button
        type="button"
        onClick={onGenerate}
        disabled={isGenerating}
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 py-2 text-[11px] font-semibold text-white transition hover:bg-[color-mix(in_oklab,var(--accent)_86%,black)] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isGenerating ? (
          <>
            <Loader2 className="animate-spin" size={14} />
            Генерация…
          </>
        ) : (
          <>
            <Download size={14} />
            Генерировать
          </>
        )}
      </button>
    </div>
  );
}

export default ReportTab;



