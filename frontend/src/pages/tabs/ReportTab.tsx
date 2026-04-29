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
    (latestRun.status === "completed" || latestRun.status === "completed_with_errors");

  const isGenerating = requestExport.isPending;

  const statusErrorMessage = useMemo(() => {
    const err = exportStatusError as any;
    return (
      err?.response?.data?.detail ||
      err?.message ||
      null
    );
  }, [exportStatusError]);

  const handleGenerate = async (exportType: ExportType) => {
    setLastError(null);

    if (!latestRun?.id) {
      setLastError("Анализ не завершён. Запустите анализ на вкладке «Обзор».");
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
      <div className="flex flex-col items-center justify-center rounded-lg bg-gray-50 py-20 text-center">
        <FileText size={48} className="mb-4 text-gray-300" />
        <h2 className="mb-2 text-xl font-semibold text-gray-900">
          Отчёт будет доступен после завершения анализа
        </h2>
        <p className="text-gray-500">
          Экспорт доступен для run со статусом completed или completed_with_errors.
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
    (typeof exportData?.error_message === "string" && exportData.error_message.trim()) ||
    "Экспорт завершился ошибкой. Попробуйте ещё раз или проверьте backend-логи.";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-gray-900">Отчёт</h2>
        <p className="mt-1 text-sm text-gray-500">
          Выберите формат и нажмите «Генерировать».
        </p>

        <div className="mt-3 space-y-0.5 text-xs text-gray-500">
          <p>
            Анализ: run {latestRun.id} · статус: {latestRun.status}
          </p>

          {latestRun.profile && (
            <p>
              Профиль анализа:{" "}
              <span className="font-medium text-gray-700">
                {latestRun.profile}
              </span>
            </p>
          )}

          {renderChecksModeLabel() && (
            <p>
              Режим проверок:{" "}
              <span className="font-medium text-gray-700">
                {renderChecksModeLabel()}
              </span>
            </p>
          )}

          {latestRun.pipeline_strategy && (
            <p>
              Стратегия пайплайна:{" "}
              <span className="font-medium text-gray-700">
                {latestRun.pipeline_strategy}
              </span>
            </p>
          )}
        </div>
      </div>

      <div className="text-xs text-gray-500">
        Отчёты ниже будут сгенерированы по последнему завершённому анализу
        {renderChecksModeLabel() || latestRun.pipeline_strategy ? ": " : "."}
        {renderChecksModeLabel() && (
          <>
            {" "}
            режим проверок{" "}
            <span className="font-medium text-gray-700">
              {renderChecksModeLabel()}
            </span>
          </>
        )}
        {latestRun.pipeline_strategy && (
          <>
            {renderChecksModeLabel() && " · "}
            стратегия пайплайна{" "}
            <span className="font-medium text-gray-700">
              {latestRun.pipeline_strategy}
            </span>
          </>
        )}
      </div>

      {lastError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {lastError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ExportCard
          title="DD Grid"
          description="Полная таблица результатов проверок с цветовым кодированием severity."
          icon={<FileSpreadsheet size={24} className="text-green-600" />}
          format="Excel (.xlsx)"
          onGenerate={() => handleGenerate("grid_xlsx")}
          isGenerating={isGenerating}
        />

        <ExportCard
          title="Deal Summary"
          description="KPI, Top Risks, разбивка по типам документов и список запросов."
          icon={<FileSpreadsheet size={24} className="text-blue-600" />}
          format="Excel (.xlsx)"
          onGenerate={() => handleGenerate("deal_summary_xlsx")}
          isGenerating={isGenerating}
        />

        <ExportCard
          title="Отчёт DD"
          description="Executive Summary, критические находки, качество анализа, запросы."
          icon={<FileText size={24} className="text-indigo-600" />}
          format="Word (.docx)"
          onGenerate={() => handleGenerate("report_docx")}
          isGenerating={isGenerating}
        />
      </div>

      {activeExportId && (
        <div className="rounded-lg border bg-white p-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="font-semibold text-gray-900">Статус экспорта</h3>

            {isFetchingExportStatus && (
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <RefreshCw size={14} className="animate-spin" />
                <span>Обновление статуса</span>
              </div>
            )}
          </div>

          {statusErrorMessage ? (
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
              <AlertCircle size={20} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="font-medium">Не удалось получить статус экспорта</div>
                <div className="text-sm">{statusErrorMessage}</div>
              </div>
            </div>
          ) : !exportData ||
            exportData.status === "processing" ||
            exportData.status === "pending" ? (
            <div className="flex items-center gap-3 text-blue-600">
              <Loader2 className="animate-spin" size={20} />
              <span>Генерация файла… Обычно занимает 10–30 секунд.</span>
            </div>
          ) : exportData.status === "completed" ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-green-600">
                <CheckCircle size={20} />
                <span className="font-medium">
                  {exportTitle} готов
                </span>
                {typeof exportData.file_size_bytes === "number" && (
                  <span className="text-xs text-gray-400">
                    ({Math.round(exportData.file_size_bytes / 1024)} КБ)
                  </span>
                )}
              </div>

              <button
                onClick={handleDownload}
                disabled={!exportData.download_url}
                className="flex items-center gap-2 rounded-lg bg-green-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Download size={16} />
                Скачать файл
              </button>
            </div>
          ) : exportData.status === "failed" ? (
            <div className="space-y-3">
              <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
                <AlertCircle size={20} className="mt-0.5 shrink-0" />
                <div className="space-y-1">
                  <div className="font-medium">
                    {exportTitle ? `${exportTitle}: ошибка генерации` : "Ошибка генерации экспорта"}
                  </div>
                  <div className="text-sm">{exportFailedMessage}</div>
                </div>
              </div>

              <div className="text-xs text-gray-500">
                Можно повторить генерацию того же формата после устранения причины ошибки.
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-amber-700">
              <AlertCircle size={20} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="font-medium">Неожиданный статус экспорта</div>
                <div className="text-sm">
                  Получен статус: <span className="font-semibold">{exportData.status}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

function ExportCard({
  title,
  description,
  icon,
  format,
  onGenerate,
  isGenerating,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  format: string;
  onGenerate: () => void;
  isGenerating: boolean;
}) {
  return (
    <div className="space-y-3 rounded-lg border bg-white p-5 transition hover:shadow-md">
      <div className="flex items-center gap-3">
        {icon}
        <div>
          <h4 className="font-semibold text-gray-900">{title}</h4>
          <p className="text-xs text-gray-400">{format}</p>
        </div>
      </div>

      <p className="text-sm text-gray-600">{description}</p>

      <button
        onClick={onGenerate}
        disabled={isGenerating}
        className="flex w-full items-center justify-center gap-2 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
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



