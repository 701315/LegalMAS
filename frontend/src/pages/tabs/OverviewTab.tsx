// =============================================================
// src/pages/tabs/OverviewTab.tsx
// Вкладка "Обзор" сделки + прогресс Run + карточка качества классификации.
// =============================================================

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { Deal } from "../../types";
import {
  useClassificationReport,
  useStartRun,
  useRun,
} from "../../api/runs";
import { ClassificationBadge } from "../../components/ui/ClassificationBadge";
import { useDealPermissions } from "../../hooks/usePermissions";

import type { RunStatus } from "../../types";
import { RUN_STATUS_CONFIG } from "../../utils/statusConfig";

interface OverviewTabProps {
  deal: Deal;
  /** ID последнего run по сделке (может быть null/undefined) */
  latestRunId?: string | null;
  /** Открыть форму настройки профиля модели */
  onOpenModelConfig?: () => void;
}

/**
 * Карточка качества классификации:
 * - мини-статистика L0–L4
 * - список документов с низкой уверенностью
 */
const ClassificationQualityCard: React.FC<{
  dealId: string;
  latestRunId?: string | null;
}> = ({ dealId, latestRunId }) => {
  const { canViewClassificationReport } = useDealPermissions(dealId);

  const runIdForQuery = canViewClassificationReport
    ? latestRunId ?? null
    : null;

  const {
    data: classReport,
    isLoading,
    error,
  } = useClassificationReport(runIdForQuery);

  if (!canViewClassificationReport) {
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
  const hasLowConfidence = lowCount > 0;

  return (
    <div className="bg-white rounded-lg p-5 border">
      <h3 className="font-semibold text-gray-900 mb-1">
        Классификация документов
      </h3>
      <p className="text-xs text-gray-500 mb-4">
        Отчёт по качеству классификации документов в последнем анализе.
      </p>

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
 * Карточка прогресса текущего Run (status + completed/total).
 */
const RunProgressCard: React.FC<{
  latestRunId?: string | null;
}> = ({ latestRunId }) => {
  const runId = latestRunId ?? null;
  const { data: run, isLoading } = useRun(runId, false);

  if (!runId) {
    return (
      <div className="bg-white rounded-lg p-5 border">
        <h3 className="text-sm font-semibold text-gray-900 mb-1">
          Статус анализа
        </h3>
        <p className="text-xs text-gray-500">
          Анализ ещё не запускался для этой сделки.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg p-5 border">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900">
          Статус анализа
        </h3>
        {isLoading ? (
          <span className="text-xs text-gray-400">Обновляем…</span>
        ) : (
          <span className="text-xs text-gray-500">
            {run?.status
              ? RUN_STATUS_CONFIG[run.status as RunStatus]?.label ?? run.status
              : "unknown"}
          </span>
        )}
      </div>

      {run && run.total_checks > 0 ? (
        <>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-gray-500">
              {run.completed_checks} из {run.total_checks} документов проверено
            </span>
            <span className="font-semibold text-gray-700">
              {Math.round(
                (run.completed_checks / run.total_checks) * 100,
              )}
              %
            </span>
          </div>
          <div className="w-full h-2 bg-gray-100 rounded">
            <div
              className={`h-2 rounded ${
                run.status === "failed"
                  ? "bg-red-500"
                  : run.status === "completed"
                  ? "bg-green-500"
                  : run.status === "completed_with_errors"
                  ? "bg-yellow-500"
                  : "bg-blue-500"
              }`}
              style={{
                width: `${Math.min(
                  100,
                  (run.completed_checks / run.total_checks) * 100,
                )}%`,
              }}
            />
          </div>
          {(run.status === "failed" ||
            run.status === "completed_with_errors") && (
            <p
              className={`mt-2 text-xs ${
                run.status === "failed" ? "text-red-600" : "text-yellow-700"
              }`}
            >
              {run.status === "failed"
                ? "Анализ завершился с ошибкой."
                : "Анализ завершён, но есть документы с ошибками."}
              {run.status === "completed_with_errors" && (
                <>
                  {" "}
                  {typeof run.failed_docs_count === "number" &&
                    run.failed_docs_count > 0 && (
                      <>Проблемных документов (FAILED): {run.failed_docs_count}. </>
                    )}
                  {typeof run.quarantine_docs_count === "number" &&
                    run.quarantine_docs_count > 0 && (
                      <>Документов в карантине: {run.quarantine_docs_count}. </>
                    )}
                </>
              )}
              {run.error_details && (run.error_details as any).message && (
                <>
                  {" "}
                  Детали: {String((run.error_details as any).message)}
                </>
              )}
            </p>
          )}
        </>
      ) : (
        <p className="text-xs text-gray-500">
          Документы для анализа ещё не готовы или пайплайн не запущен.
        </p>
      )}
    </div>
  );
};

/**
 * Основной компонент вкладки Overview.
 */
const OverviewTab: React.FC<OverviewTabProps> = ({
  deal,
  latestRunId,
  onOpenModelConfig,
}) => {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const startRun = useStartRun(deal.id);
  const { canStartRun } = useDealPermissions(deal.id);

  const handleStart = () => {
    if (!canStartRun) {
      return;
    }

    // Защита: без выбранного плейбука анализ не запускаем
    if (!deal.playbook_version_id) {
      window.alert("Сначала выбери плейбук для сделки");
      navigate(`/projects/${deal.id}/playbook`);
      return;
    }

    const forceKey = `mas_dd_force_reclassify_${deal.id}`;
    const forceReclassify =
      typeof window !== "undefined" &&
      window.localStorage.getItem(forceKey) === "1";

    startRun.mutate(
      {
        profile: "core",
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: (run) => {
          if (typeof window !== "undefined") {
            window.localStorage.removeItem(forceKey);
          }
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

  const handleOpenPlaybook = () => {
    navigate(`/projects/${deal.id}/playbook`);
  };

  const hasPlaybook = !!deal.playbook_version_id;

  return (
    <div className="space-y-4">
      {/* Заголовок / краткая информация о сделке */}
      <div className="bg-white rounded-lg p-5 border space-y-3">
        <div className="flex items-center justify-between">
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
            className={`px-3 py-1.5 rounded text-xs ${
              canStartRun
                ? "bg-blue-600 text-white hover:bg-blue-700"
                : "bg-gray-200 text-gray-400 cursor-not-allowed"
            }`}
            onClick={handleStart}
            disabled={!canStartRun || startRun.isPending}
          >
            {startRun.isPending ? "Запускаем…" : "Запустить анализ"}
          </button>
        </div>

        {/* Краткая информация о playbook проекта */}
        <div className="flex flex-col gap-1 text-xs pt-2 border-t border-gray-100">
          <div className="flex items-center justify-between">
            <div className="text-gray-600">
              <span className="font-semibold">Playbook проекта:</span>{" "}
              {hasPlaybook ? (
                <span>выбран (версия ID: {deal.playbook_version_id})</span>
              ) : (
                <span className="text-gray-500">не выбран</span>
              )}
            </div>
            <button
              type="button"
              onClick={handleOpenPlaybook}
              className="px-3 py-1 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
            >
              Настроить playbook
            </button>
          </div>

          <div className="text-gray-600 flex items-center justify-between">
            <div>
              <span className="font-semibold">Профиль модели:</span>{" "}
              {deal.model_config_name ? (
                <span>{deal.model_config_name}</span>
              ) : (
                <span className="text-gray-500">
                  не указан (зависит от выбранного playbook)
                </span>
              )}
            </div>

            {onOpenModelConfig && (
              <button
                type="button"
                onClick={onOpenModelConfig}
                className="ml-4 px-3 py-1 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 text-xs"
              >
                Настроить профиль модели
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Прогресс текущего Run */}
      <RunProgressCard latestRunId={latestRunId} />

      {/* Карточка качества классификации */}
      <ClassificationQualityCard dealId={deal.id} latestRunId={latestRunId} />
    </div>
  );
};

export default OverviewTab;
