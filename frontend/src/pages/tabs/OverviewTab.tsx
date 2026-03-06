// =============================================================
// src/pages/tabs/OverviewTab.tsx
// Вкладка "Обзор" сделки + карточка качества классификации.
// =============================================================

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Deal } from "../../types";
import { useClassificationReport, useStartRun } from "../../api/runs";
import { ClassificationBadge } from "../../components/ui/ClassificationBadge";
import { canViewClassificationReport } from "../../constants";

// Временный хук авторизации: позже заменим на реальный useAuth
function useAuth() {
  // TODO: заменить на реальный Zustand-стор / контекст
  const userRole = "editor" as const;
  return { userRole };
}

interface OverviewTabProps {
  deal: Deal;
  /** ID последнего run по сделке (может быть null/undefined) */
  latestRunId?: string | null;
}

/**
 * Карточка качества классификации:
 * - мини-статистика L0–L4
 * - список документов с низкой уверенностью
 */
const ClassificationQualityCard: React.FC<{
  latestRunId?: string | null;
}> = ({ latestRunId }) => {
  const { userRole } = useAuth();

  // Если нет права или нет runId — не грузим отчёт вообще
  const canView = canViewClassificationReport(userRole);
  const runIdForQuery = canView ? latestRunId ?? null : null;

  const {
    data: classReport,
    isLoading,
    error,
  } = useClassificationReport(runIdForQuery);

  if (!canView) {
    return null;
  }

  if (!latestRunId) {
    return (
      <div className="bg-white rounded-lg p-5 border">
        <h3 className="font-semibold text-gray-900 mb-1">
          Классификация документов
        </h3>
        <p className="text-xs text-gray-500">
          Отчёт недоступен: для сделки ещё не запускался анализ (нет run).
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg p-5 border">
        <h3 className="font-semibold text-gray-900 mb-1">
          Классификация документов
        </h3>
        <p className="text-xs text-gray-500">
          Загружаем отчёт по классификации…
        </p>
      </div>
    );
  }

  if (error || !classReport) {
    return (
      <div className="bg-white rounded-lg p-5 border">
        <h3 className="font-semibold text-gray-900 mb-1">
          Классификация документов
        </h3>
        <p className="text-xs text-red-500">
          Не удалось загрузить отчёт по классификации.
        </p>
      </div>
    );
  }

  const stats = classReport.stats;
  const lowCount = stats.low_confidence_count;

  // Если low_confidence документов нет — просто показываем краткую статистику
  const hasLowConfidence = lowCount > 0;

  return (
    <div className="bg-white rounded-lg p-5 border">
      <h3 className="font-semibold text-gray-900 mb-1">
        Классификация документов
      </h3>
      <p className="text-xs text-gray-500 mb-4">
        Отчёт по качеству классификации документов в последнем анализе.
      </p>

      {/* Мини-статистика по уровням L0–L4 */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        {[
          { key: "l4_llm", label: "L4 LLM", color: "text-green-700" },
          { key: "l3_semantic", label: "L3 Семантика", color: "text-purple-700" },
          { key: "l2_keyword", label: "L2 Ключевые слова", color: "text-indigo-700" },
          { key: "l1_filename", label: "L1 Имя файла", color: "text-blue-700" },
          { key: "l0_no_match", label: "L0 Нет совпадений", color: "text-gray-500" },
        ].map(({ key, label, color }) => {
          const count = stats[key as keyof typeof stats] as number;
          if (!count) return null;
          return (
            <div key={key} className="text-center p-2 bg-gray-50 rounded">
              <p className={`text-lg font-bold ${color}`}>{count}</p>
              <p className="text-xs text-gray-500">{label}</p>
            </div>
          );
        })}
      </div>

      {/* Блок документов с низкой уверенностью */}
      {hasLowConfidence ? (
        <div>
          <p className="text-xs font-semibold text-yellow-800 mb-2">
            ⚠️ {lowCount} документ(ов) с низкой уверенностью (&lt; 60%):
          </p>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {classReport.low_confidence_docs.slice(0, 5).map((doc) => (
              <div
                key={doc.doc_id}
                className="flex items-center justify-between
                           text-xs bg-yellow-50 px-3 py-1.5 rounded"
              >
                <span className="truncate text-gray-700 max-w-[60%]">
                  {doc.filename}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-gray-500">
                    {doc.doc_type || "Generic"}
                  </span>
                  <ClassificationBadge
                    level={doc.classification_level as any}
                    confidence={doc.confidence}
                  />
                </div>
              </div>
            ))}
          </div>
          {classReport.low_confidence_docs.length > 5 && (
            <p className="text-xs text-gray-400 mt-1 text-right">
              и ещё {classReport.low_confidence_docs.length - 5} документ(ов)…
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-green-700">
          Все документы классифицированы с достаточной уверенностью.
        </p>
      )}
    </div>
  );
};

/**
 * Основной компонент вкладки Overview.
 * Содержит заголовок, кнопку запуска и ClassificationQualityCard.
 */
const OverviewTab: React.FC<OverviewTabProps> = ({ deal, latestRunId }) => {
  const qc = useQueryClient();
  const startRun = useStartRun(deal.id);

  const handleStart = () => {
    const forceKey = `mas_dd_force_reclassify_${deal.id}`;
    const forceReclassify =
      typeof window !== "undefined" &&
      window.localStorage.getItem(forceKey) === "1";

    startRun.mutate(
      {
        // RunCreateInput: profile и force_reclassify, playbook выбирается по сделке
        profile: "core",
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: (run) => {
          if (typeof window !== "undefined") {
            window.localStorage.removeItem(forceKey);
          }
          // Обновить информацию о текущем run
          qc.invalidateQueries({
            queryKey: ["run", run.id, true],
          });
          qc.invalidateQueries({
            queryKey: ["run", run.id, false],
          });
          qc.invalidateQueries({
            queryKey: ["classification-report", run.id],
          });
          qc.invalidateQueries({ 
            queryKey: ["deal", deal.id],
          });

        },
      },
    );
  };

  return (
    <div className="space-y-4">
      {/* Заголовок / краткая информация о сделке */}
      <div className="bg-white rounded-lg p-5 border flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 mb-1">
            Обзор сделки
          </h1>
          <p className="text-sm text-gray-600">
            {deal.name} · статус: {deal.status}
          </p>
        </div>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-blue-600 text-white text-xs hover:bg-blue-700"
          onClick={handleStart}
        >
          Запустить анализ
        </button>
      </div>

      {/* Карточка качества классификации */}
      <ClassificationQualityCard latestRunId={latestRunId} />
    </div>
  );
};

export default OverviewTab;
