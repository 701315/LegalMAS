// =============================================================
// src/pages/tabs/ReportTab.tsx
// Вкладка «Отчёт»:
// - запуск экспорта (Excel/Word)
// - отслеживание статуса
// - скачивание готового файла
// =============================================================

import React, { useState } from "react";
import { useLatestRun } from "../../api/results";
import { useRequestExport, useExportStatus } from "../../api/exports";
import { EXPORT_TYPE_LABEL } from "../../constants";

import {
  FileText,
  Download,
  Loader2,
  CheckCircle,
  AlertCircle,
  FileSpreadsheet,
} from "lucide-react";

interface Props {
  dealId: string;
}

export const ReportTab: React.FC<Props> = ({ dealId }) => {
  const { data: latestRun } = useLatestRun(dealId);
  const requestExport = useRequestExport();

  const [activeExportId, setActiveExportId] = useState<string | null>(null);
  const { data: exportData } = useExportStatus(activeExportId);

  const handleGenerate = async (exportType: string) => {
    if (!latestRun?.id) {
      alert("Анализ не завершён. Запустите анализ на вкладке «Обзор».");
      return;
    }
    try {
      const exp = await requestExport.mutateAsync({
        runId: latestRun.id,
        exportType,
      });
      setActiveExportId(exp.id);
    } catch {
      alert("Ошибка запроса экспорта");
    }
  };

  const handleDownload = () => {
    if (exportData?.download_url) {
      window.open(exportData.download_url, "_blank");
    }
  };

  if (
    !latestRun ||
    (latestRun.status !== "completed" &&
      latestRun.status !== "completed_with_errors")
  ) {
    return (
      <div className="flex flex-col items-center justify-center bg-gray-50 rounded-lg py-20 text-center">
        <FileText size={48} className="text-gray-300 mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 mb-2">
          Отчёт будет доступен после завершения анализа
        </h2>
        <p className="text-gray-500">
          Перейдите на вкладку «Обзор» и запустите анализ
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900">Отчёт</h2>
        <p className="text-sm text-gray-500 mt-1">
          Выберите формат и нажмите «Генерировать».
        </p>
      </div>

      {/* Карточки экспорта */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ExportCard
          title="DD Grid"
          description="Полная таблица результатов проверок с цветовым кодированием severity."
          icon={<FileSpreadsheet size={24} className="text-green-600" />}
          format="Excel (.xlsx)"
          onGenerate={() => handleGenerate("grid_xlsx")}
          isGenerating={requestExport.isPending}
        />

        <ExportCard
          title="Deal Summary"
          description="KPI, Top Risks, разбивка по типам документов и список запросов."
          icon={<FileSpreadsheet size={24} className="text-blue-600" />}
          format="Excel (.xlsx)"
          onGenerate={() => handleGenerate("deal_summary_xlsx")}
          isGenerating={requestExport.isPending}
        />

        <ExportCard
          title="Отчёт DD"
          description="Executive Summary, критические находки, качество анализа, запросы."
          icon={<FileText size={24} className="text-indigo-600" />}
          format="Word (.docx)"
          onGenerate={() => handleGenerate("report_docx")}
          isGenerating={requestExport.isPending}
        />
      </div>

      {/* Статус текущего экспорта */}
      {activeExportId && (
        <div className="border rounded-lg p-5 bg-white">
          <h3 className="font-semibold text-gray-900 mb-3">
            Статус экспорта
          </h3>

          {!exportData || exportData.status === "processing" ? (
            <div className="flex items-center gap-3 text-blue-600">
              <Loader2 className="animate-spin" size={20} />
              <span>Генерация файла… Обычно занимает 10–30 секунд.</span>
            </div>
          ) : exportData.status === "completed" ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-green-600">
                <CheckCircle size={20} />
                <span className="font-medium">
                {EXPORT_TYPE_LABEL[exportData.export_type] || exportData.export_type} готов
                </span>
                <span className="text-xs text-gray-400">
                  ({Math.round(exportData.file_size_bytes / 1024)} КБ)
                </span>
              </div>
              <button
                onClick={handleDownload}
                className="flex items-center gap-2 px-6 py-2.5 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700 transition"
              >
                <Download size={16} />
                Скачать файл
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 text-red-600">
              <AlertCircle size={20} />
              <span>Ошибка генерации. Попробуйте ещё раз.</span>
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
    <div className="border rounded-lg p-5 bg-white hover:shadow-md transition space-y-3">
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
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 transition disabled:opacity-50"
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
