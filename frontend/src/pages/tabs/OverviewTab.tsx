// =============================================================
// src/pages/tabs/OverviewTab.tsx
// Вкладка "Обзор" сделки + прогресс Run + карточка качества классификации.
// =============================================================

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { Deal, RunStatus } from "../../types";
import {
  useClassificationReport,
  useStartRun,
  useRun,
} from "../../api/runs";
import { useSetPrimaryLanguage } from "../../api/deals";
import { ClassificationBadge } from "../../components/ui/ClassificationBadge";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useSSEProgress } from "../../hooks/useSSE";
import { RUN_STATUS_CONFIG } from "../../utils/statusConfig";
import type { ClassificationLevel } from "../../types";

// Если используешь toast, раскомментируй:
// import { toast } from "react-hot-toast";

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
          {
            key: "l3_semantic",
            label: "L3 Семантика",
            color: "text-purple-700",
          },
          {
            key: "l2_keyword",
            label: "L2 Ключевые слова",
            color: "text-indigo-700",
          },
          { key: "l1_filename", label: "L1 Имя файла", color: "text-blue-700" },
          {
            key: "l0_no_match",
            label: "L0 Нет совпадений",
            color: "text-gray-500",
          },
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
                className="flex items-center justify-between text-xs bg-yellow-50 px-3 py-1.5 rounded"
              >
                <span className="truncate text-gray-700 max-w-[60%]">
                  {doc.filename}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-gray-500">
                    {doc.doc_type || "Generic"}
                  </span>
                  <ClassificationBadge
                    level={doc.classification_level as ClassificationLevel}
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
 * Использует run + SSE для живого обновления.
 */
const RunProgressCard: React.FC<{
  latestRunId?: string | null;
}> = ({ latestRunId }) => {
  const runId = latestRunId ?? null;
  const { data: run, isLoading } = useRun(runId, false);
  const { lastEvent } = useSSEProgress(runId, { enabled: !!runId });

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

  const effectiveCompleted =
    lastEvent?.completed_checks ?? run?.completed_checks ?? 0;
  const effectiveTotal = lastEvent?.total_checks ?? run?.total_checks ?? 0;
  const effectiveStatus = (lastEvent?.status ??
    run?.status) as RunStatus | undefined;

  const percent =
    effectiveTotal > 0
      ? Math.round((effectiveCompleted / effectiveTotal) * 100)
      : 0;

  return (
    <div className="bg-white rounded-lg p-5 border">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900">
          Статус анализа
        </h3>
        {isLoading && !run ? (
          <span className="text-xs text-gray-400">Загружаем…</span>
        ) : (
          <span className="text-xs text-gray-500">
            {effectiveStatus
              ? RUN_STATUS_CONFIG[effectiveStatus]?.label ?? effectiveStatus
              : "unknown"}
          </span>
        )}
      </div>

      {/* Доп. информация о режиме и стратегии запуска */}
      {run && (
        <div className="mb-2 text-xs text-gray-500 space-y-0.5">
          {run.checks_mode && (
            <p>
              Режим проверок:{" "}
              <span className="font-medium text-gray-700">
                {run.checks_mode === "global_and_doc_type"
                  ? "Плейбук + типы документов"
                  : run.checks_mode === "global_only"
                  ? "Только плейбук"
                  : "Только типы документов"}
              </span>
            </p>
          )}
          {run.pipeline_strategy && (
            <p>
              Стратегия пайплайна:{" "}
              <span className="font-medium text-gray-700">
                {run.pipeline_strategy}
              </span>
            </p>
          )}
        </div>
      )}

      {effectiveTotal > 0 ? (
        <>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-gray-500">
              В загруженных документах проведено {effectiveTotal} проверок
            </span>
            <span className="font-semibold text-gray-700">{percent}%</span>
          </div>
          <div className="w-full h-2 bg-gray-100 rounded">
            <div
              className={`h-2 rounded ${
                effectiveStatus === "failed"
                  ? "bg-red-500"
                  : effectiveStatus === "completed"
                  ? "bg-green-500"
                  : effectiveStatus === "completed_with_errors"
                  ? "bg-yellow-500"
                  : "bg-blue-500"
              }`}
              style={{
                width: `${Math.min(100, percent)}%`,
              }}
            />
          </div>
          {(effectiveStatus === "failed" ||
            effectiveStatus === "completed_with_errors") &&
            run && (
              <p
                className={`mt-2 text-xs ${
                  effectiveStatus === "failed"
                    ? "text-red-600"
                    : "text-yellow-700"
                }`}
              >
                {effectiveStatus === "failed"
                  ? "Анализ завершился с ошибкой."
                  : "Анализ завершён, но есть документы с ошибками."}
                {effectiveStatus === "completed_with_errors" && (
                  <>
                    {" "}
                    {typeof run.failed_docs_count === "number" &&
                      run.failed_docs_count > 0 && (
                        <>
                          Проблемных документов (FAILED):{" "}
                          {run.failed_docs_count}.{" "}
                        </>
                      )}
                    {typeof run.quarantine_docs_count === "number" &&
                      run.quarantine_docs_count > 0 && (
                        <>
                          Документов в карантине:{" "}
                          {run.quarantine_docs_count}.{" "}
                        </>
                      )}
                  </>
                )}

                {(() => {
                  const details = run.error_details;
                  if (
                    details &&
                    typeof details === "object" &&
                    "message" in details &&
                    typeof (details as { message: unknown }).message === "string"
                  ) {
                    return (
                      <>
                        {" "}
                        Детали: {(details as { message: string }).message}
                      </>
                    );
                  }
                  return null;
                })()}
              </p>
            )}
          {effectiveStatus === "running" && (
            <p className="mt-2 text-xs text-gray-500">
              Переклассифицированные документы будут учтены в этом анализе.
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
  const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);

  // Подтянем данные последнего Run, если он есть, чтобы показать режим/стратегию
  const { data: latestRun } = useRun(latestRunId ?? null, false);

  const readableChecksMode =
    latestRun?.checks_mode === "global_and_doc_type"
      ? "Плейбук + типы документов"
      : latestRun?.checks_mode === "global_only"
      ? "Только плейбук"
      : latestRun?.checks_mode === "doc_type_only"
      ? "Только типы документов"
      : null;

  // Локальное состояние выбора режима проверок
  const [checksMode, setChecksMode] = React.useState<
    "global_only" | "doc_type_only" | "global_and_doc_type"
  >("global_and_doc_type");

  // Локальный флаг: перезапустили ли уже анализ после переклассификации
  const [hasRestartedAfterReclass, setHasRestartedAfterReclass] =
    React.useState(false);

  const showReclassBanner =
    deal.has_pending_manual_reclassifications && !hasRestartedAfterReclass;

  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const selectedPrimaryLanguage = deal.primary_language ?? "";
  const isAutoLanguage = !selectedPrimaryLanguage;

  const shouldShowLanguageWarning =
    hasMultipleDocumentLanguages && isAutoLanguage;

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

    if (hasMultipleDocumentLanguages && isAutoLanguage) {
      const confirmed = window.confirm(
        `Для этой сделки обнаружены документы на нескольких языках: ${documentLanguages.join(
          ", ",
        )}.\n\n` +
          "Основной язык анализа не зафиксирован и будет использован русский язык по умолчанию.\n\n" +
          "Если вы продолжите, дальнейшая обработка многоязычных документов (приведение к одноязычности, экстракция, санитизация, построение структуры, чанкинг и классификация) будет выполняться с опорой на русский язык.\n\n" +
          "Подтвердить и запустить анализ?",
      );

      if (!confirmed) {
        return;
      }
    }

    const forceKey = `mas_dd_force_reclassify_${deal.id}`;
    const forceReclassify =
      typeof window !== "undefined" &&
      window.localStorage.getItem(forceKey) === "1";

    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: (run) => {
          if (typeof window !== "undefined") {
            window.localStorage.removeItem(forceKey);
          }

          // Скрываем баннер о необходимости перезапуска
          setHasRestartedAfterReclass(true);

          // Ненавязчивая нотификация (замени на свой toast)
          // toast.success(
          //   "Запущен новый анализ. Следи за прогрессом в блоке 'Статус анализа'.",
          // );

          qc.invalidateQueries({ queryKey: ["run", run.id, true] });
          qc.invalidateQueries({ queryKey: ["run", run.id, false] });
          qc.invalidateQueries({
            queryKey: ["classification-report", run.id],
          });
          qc.invalidateQueries({ queryKey: ["deal", deal.id] });
          qc.invalidateQueries({ queryKey: ["latest-run", deal.id, true] });
          qc.invalidateQueries({ queryKey: ["latest-run", deal.id, false] });
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
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 mb-1">
              Обзор сделки
            </h1>
            <p className="text-sm text-gray-600">
              {deal.name} · статус: {deal.status}
            </p>

            {/* Краткий контекст последнего анализа: режим и стратегия */}
            {latestRun && (
              <p className="mt-1 text-xs text-gray-500">
                Последний анализ:{" "}
                {readableChecksMode && (
                  <>
                    режим проверок{" "}
                    <span className="font-medium text-gray-700">
                      {readableChecksMode}
                    </span>
                  </>
                )}
                {latestRun.pipeline_strategy && (
                  <>
                    {readableChecksMode && " · "}
                    стратегия пайплайна{" "}
                    <span className="font-medium text-gray-700">
                      {latestRun.pipeline_strategy}
                    </span>
                  </>
                )}
              </p>
            )}
          </div>

          <div className="flex flex-col items-stretch gap-2 md:items-end">
            {/* Выпадающий список режима проверок */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-500">Режим проверок:</span>
              <select
                value={checksMode}
                onChange={(e) =>
                  setChecksMode(
                    e.target.value as
                      | "global_only"
                      | "doc_type_only"
                      | "global_and_doc_type",
                  )
                }
                disabled={!canStartRun || startRun.isPending}
                className="border rounded px-2 py-1 text-xs text-gray-700 bg-white disabled:opacity-50"
              >
                <option value="global_and_doc_type">
                  Плейбук + типы документов
                </option>
                <option value="global_only">Только плейбук</option>
                <option value="doc_type_only">Только типы документов</option>
              </select>
            </div>

            {/* Кнопка запуска анализа */}
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
        </div>

        {showReclassBanner && (
          <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 max-w-xl">
            <p className="text-xs text-red-700">
              Перезапусти анализ документов, т.к. была произведена
              переклассификация документа. Анализ рисков по новому типу
              документа будет произведён только после перезапуска анализа
              рисков по всей сделке. Текущее состояние архитектуры. После
              будет внедрён механизм отдельного пересмотра рисков по отдельному
              документу после его переклассификации.
            </p>
          </div>
        )}

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

          {/* Языки документов и выбор основного языка */}
          <div className="mt-2 flex flex-col gap-1 text-xs text-gray-600">
            <div>
              <span className="font-semibold">Языки документов:</span>{" "}
              {deal.languages && deal.languages.length > 0 ? (
                <span>{deal.languages.join(", ")}</span>
              ) : (
                <span className="text-gray-500">RU (по умолчанию)</span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <span className="font-semibold">Основной язык для анализа:</span>
              <select
                className="border rounded px-2 py-1 text-xs bg-white text-gray-700 disabled:opacity-50"
                value={deal.primary_language ?? ""}
                onChange={(e) => {
                  const value = e.target.value || null;
                  setPrimaryLanguage.mutate({ primary_language: value });
                }}
                disabled={
                  !deal.languages ||
                  deal.languages.length === 0 ||
                  setPrimaryLanguage.isPending
                }
              >
                {/* Пустое значение = автоматический выбор на стороне backend-а.
                   Там мы используем RU по умолчанию или единственный язык из списка. */}
                <option value="">
                  Авто (RU по умолчанию)
                </option>
                {deal.languages?.map((lang) => (
                  <option key={lang} value={lang}>
                    {lang}
                  </option>
                ))}
              </select>
            </div>

            <p className="text-[11px] text-gray-400">
              Основной язык влияет на распознавание структуры документов и работу моделей.
            </p>

            {shouldShowLanguageWarning && (
              <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-3 py-2">
                <p className="text-xs font-semibold text-amber-900">
                  ⚠️ Для сделки обнаружены документы на нескольких языках:{" "}
                  {documentLanguages.join(", ")}.
                </p>
                <p className="mt-1 text-xs leading-5 text-amber-800">
                  Для многоязычных документов дальнейшая обработка —
                  приведение к одноязычности по выбранному основному языку
                  проверки, а также экстракция, санитизация, построение
                  структуры, чанкинг и классификация — зависит от выбранного
                  основного языка. По умолчанию будет использован русский язык.
                  При необходимости выбери другой основной язык перед запуском анализа.
                </p>
              </div>
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

