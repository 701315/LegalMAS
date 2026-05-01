// =============================================================
// src/pages/tabs/OverviewTab.tsx
// Вкладка "Обзор" сделки: контекст проекта, статус анализа,
// качество классификации. Справа — action panel.
// При запуске открывается overlay-панель влево, поверх
// левой колонки с обзорными блоками.
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { Deal, RunStatus, ClassificationLevel } from "../../types";
import {
  useClassificationReport,
  useRun,
  useStartRun,
} from "../../api/runs";
import { useSetPrimaryLanguage } from "../../api/deals";
import { useDocumentsCount } from "../../api/documents";
import { ClassificationBadge } from "../../components/ui/ClassificationBadge";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useSSEProgress } from "../../hooks/useSSE";
import { RUN_STATUS_CONFIG } from "../../utils/statusConfig";
import Button from "../../components/ui/Button";

type ChecksMode = "global_only" | "doc_type_only" | "global_and_doc_type";

interface OverviewTabProps {
  deal: Deal;
  latestRunId?: string | null;
  onOpenModelConfig?: () => void;
}

const SECONDARY_ACTION_BUTTON_CLASS =
  "w-[220px] shrink-0 justify-center whitespace-nowrap text-sm font-semibold";

const ClassificationQualityCard: React.FC<{
  dealId: string;
  latestRunId?: string | null;
}> = ({ dealId, latestRunId }) => {
  const { canViewClassificationReport } = useDealPermissions(dealId);

  const runIdForQuery = canViewClassificationReport ? latestRunId ?? null : null;

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
      <div className="rounded-lg border bg-white p-5">
        <h3 className="mb-1 font-semibold text-gray-900">
          Классификация документов
        </h3>
        <p className="text-xs text-gray-500">
          Отчёт недоступен: для этой сделки ещё не запускался анализ.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="rounded-lg border bg-white p-5">
        <h3 className="mb-1 font-semibold text-gray-900">
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
      <div className="rounded-lg border bg-white p-5">
        <h3 className="mb-1 font-semibold text-gray-900">
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
    <div className="rounded-lg border bg-white p-5">
      <h3 className="mb-1 font-semibold text-gray-900">
        Классификация документов
      </h3>
      <p className="mb-4 text-xs text-gray-500">
        Сводка качества классификации документов в последнем анализе.
      </p>

      <div className="mb-4 grid grid-cols-3 gap-2">
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
            <div key={key} className="rounded bg-gray-50 p-2 text-center">
              <p className={`text-lg font-bold ${color}`}>{count}</p>
              <p className="text-xs text-gray-500">{label}</p>
            </div>
          );
        })}
      </div>

      {hasLowConfidence ? (
        <div>
          <p className="mb-2 text-xs font-semibold text-yellow-800">
            ⚠️ {lowCount} документ(ов) с низкой уверенностью (&lt; 60%).
          </p>

          <div className="max-h-40 space-y-1.5 overflow-y-auto">
            {classReport.low_confidence_docs.slice(0, 5).map((doc) => (
              <div
                key={doc.doc_id}
                className="flex items-center justify-between rounded bg-yellow-50 px-3 py-1.5 text-xs"
              >
                <span className="max-w-[60%] truncate text-gray-700">
                  {doc.filename}
                </span>

                <div className="flex shrink-0 items-center gap-2">
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
            <p className="mt-1 text-right text-xs text-gray-400">
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

const RunProgressCard: React.FC<{
  latestRunId?: string | null;
}> = ({ latestRunId }) => {
  const runId = latestRunId ?? null;
  const { data: run, isLoading } = useRun(runId, false);
  const { lastEvent } = useSSEProgress(runId, { enabled: !!runId });

  if (!runId) {
    return (
      <div className="rounded-lg border bg-white p-5">
        <h3 className="mb-1 text-sm font-semibold text-gray-900">
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
    <div className="rounded-lg border bg-white p-5">
      <div className="mb-2 flex items-center justify-between">
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

      {effectiveTotal > 0 ? (
        <>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-gray-500">
              В загруженных документах будет проведено {effectiveTotal} проверок
            </span>
            <span className="font-semibold text-gray-700">{percent}%</span>
          </div>

          <div className="h-2 w-full rounded bg-gray-100">
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
              style={{ width: `${Math.min(100, percent)}%` }}
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
                        <>Проблемных документов (FAILED): {run.failed_docs_count}. </>
                      )}
                    {typeof run.quarantine_docs_count === "number" &&
                      run.quarantine_docs_count > 0 && (
                        <>Документов в карантине: {run.quarantine_docs_count}. </>
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
                    return <> Детали: {(details as { message: string }).message}</>;
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

const StatusRow: React.FC<{
  label: string;
  value: string;
  tone?: "ok" | "warn" | "neutral";
}> = ({ label, value, tone = "neutral" }) => {
  const toneClass =
    tone === "ok"
      ? "text-green-700"
      : tone === "warn"
      ? "text-amber-700"
      : "text-gray-700";

  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-sm ${toneClass}`}>{value}</p>
    </div>
  );
};

const LaunchOverlayPanel: React.FC<{
  open: boolean;
  onClose: () => void;
  deal: Deal;
  latestRunId?: string | null;
  documentsCount?: number;
  checksMode: ChecksMode;
  onChecksModeChange: (value: ChecksMode) => void;
  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;
  canStartRun: boolean;
  canUploadDocuments: boolean;
  isSubmitting: boolean;
  onOpenPlaybook: () => void;
  onOpenModelConfig?: () => void;
  onOpenUpload: () => void;
  onPrimaryLanguageChange: (value: string) => void;
  onSubmit: () => void;
}> = ({
  open,
  onClose,
  deal,
  latestRunId,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canStartRun,
  canUploadDocuments,
  isSubmitting,
  onOpenPlaybook,
  onOpenModelConfig,
  onOpenUpload,
  onPrimaryLanguageChange,
  onSubmit,
}) => {
  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const selectedPrimaryLanguage = deal.primary_language ?? "";

  const requiresExplicitPrimaryLanguage = hasMultipleDocumentLanguages;
  const hasValidPrimaryLanguageSelection =
    !requiresExplicitPrimaryLanguage || !!selectedPrimaryLanguage;

  const hasPlaybook = !!deal.playbook_version_id;

  const canLaunchRun =
    canStartRun && hasPlaybook && hasValidPrimaryLanguageSelection && !isSubmitting;

  let readinessLabel: string;
  if (!hasPlaybook) {
    readinessLabel = "Нужно выбрать playbook, чтобы запустить анализ.";
  } else if (!hasValidPrimaryLanguageSelection) {
    readinessLabel = "Нужно выбрать основной язык анализа.";
  } else {
    readinessLabel = "Параметры готовы к запуску анализа.";
  }

  if (!open) return null;

  return (
    <>
      <div
        className="absolute inset-0 z-20 rounded-lg bg-white/55 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="absolute inset-y-0 right-[calc(100%+1rem)] z-30 hidden w-[760px] max-w-[calc(100vw-24rem)] xl:block">
        <div className="flex max-h-[calc(100vh-7rem)] flex-col rounded-lg border border-gray-200 bg-white shadow-xl">
          <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900">
                Запуск анализа
              </h3>
              <p className="mt-1 text-sm text-gray-600">
                Проверьте параметры анализа для этой сделки.
              </p>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
              aria-label="Закрыть панель запуска"
            >
              ✕
            </button>
          </div>

          <div className="space-y-3 overflow-y-auto px-5 py-4">
            <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
              <p className="text-xs font-semibold text-gray-800">
                {readinessLabel}
              </p>
              {latestRunId && (
                <p className="mt-1 text-[11px] text-gray-500">
                  Последний анализ уже запускался. Новый запуск обновит результаты
                  по текущим документам.
                </p>
              )}
            </div>

            <section className="rounded-lg border border-gray-200 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <h4 className="text-sm font-semibold text-gray-900">
                    Документы
                  </h4>
                  <p className="mt-1 text-xs text-gray-600">
                    {typeof documentsCount === "number"
                      ? `В проект загружено ${documentsCount} документ(ов).`
                      : "Загружаем информацию о документах…"}
                  </p>
                  <p className="mt-1 text-[11px] text-gray-500">
                    Для добавления новых документов используйте отдельный сценарий загрузки.
                  </p>
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onOpenUpload}
                  disabled={!canUploadDocuments}
                  className={SECONDARY_ACTION_BUTTON_CLASS}
                >
                  Загрузить документы
                </Button>
              </div>
            </section>

            <section className="rounded-lg border border-gray-200 p-4">
              <h4 className="text-sm font-semibold text-gray-900">
                Режим проверки
              </h4>

              <div className="mt-3 space-y-2">
                <label className="flex items-start gap-2 rounded border border-gray-200 px-3 py-2">
                  <input
                    type="radio"
                    className="mt-[2px]"
                    value="global_and_doc_type"
                    checked={checksMode === "global_and_doc_type"}
                    onChange={() => onChecksModeChange("global_and_doc_type")}
                    disabled={isSubmitting || !canStartRun}
                  />
                  <span>
                    <span className="block text-[13px] font-medium text-gray-900">
                      Playbook и типы документов
                    </span>
                    <span className="block text-[11px] text-gray-500">
                      Рекомендуемый режим: комбинирует глобальный playbook и типовые проверки.
                    </span>
                  </span>
                </label>

                <label className="flex items-start gap-2 rounded border border-gray-200 px-3 py-2">
                  <input
                    type="radio"
                    className="mt-[2px]"
                    value="global_only"
                    checked={checksMode === "global_only"}
                    onChange={() => onChecksModeChange("global_only")}
                    disabled={isSubmitting || !canStartRun}
                  />
                  <span>
                    <span className="block text-[13px] font-medium text-gray-900">
                      Только Playbook
                    </span>
                    <span className="block text-[11px] text-gray-500">
                      Анализ только по правилам playbook без привязки к типу документа.
                    </span>
                  </span>
                </label>

                <label className="flex items-start gap-2 rounded border border-gray-200 px-3 py-2">
                  <input
                    type="radio"
                    className="mt-[2px]"
                    value="doc_type_only"
                    checked={checksMode === "doc_type_only"}
                    onChange={() => onChecksModeChange("doc_type_only")}
                    disabled={isSubmitting || !canStartRun}
                  />
                  <span>
                    <span className="block text-[13px] font-medium text-gray-900">
                      Только типы документов
                    </span>
                    <span className="block text-[11px] text-gray-500">
                      Используются проверки, привязанные к типам документов.
                    </span>
                  </span>
                </label>
              </div>
            </section>

            <section className="rounded-lg border border-gray-200 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <h4 className="text-sm font-semibold text-gray-900">
                    Playbook проекта
                  </h4>
                  <p className="mt-1 text-xs text-gray-500">
                    Используется для формирования проверок и DD Grid.
                  </p>
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onOpenPlaybook}
                  className={SECONDARY_ACTION_BUTTON_CLASS}
                >
                  Открыть Playbook
                </Button>
              </div>

              <p className="mt-3 text-xs">
                {hasPlaybook ? (
                  <span className="text-gray-700">
                    Playbook выбран. При необходимости вы можете изменить его перед запуском.
                  </span>
                ) : (
                  <span className="text-red-600">
                    Playbook не выбран. Нельзя запустить анализ без выбранного playbook.
                  </span>
                )}
              </p>
            </section>

            <section className="rounded-lg border border-gray-200 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <h4 className="text-sm font-semibold text-gray-900">
                    Профиль модели
                  </h4>
                  <p className="mt-1 text-xs text-gray-500">
                    Настройка профиля модели для специальных сценариев анализа.
                  </p>
                </div>

                {onOpenModelConfig && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={onOpenModelConfig}
                    className={SECONDARY_ACTION_BUTTON_CLASS}
                  >
                    Настроить профиль модели
                  </Button>
                )}
              </div>

              <p className="mt-3 text-xs text-gray-700">
                {deal.model_config_name
                  ? `Текущий профиль: ${deal.model_config_name}.`
                  : "Будет использован профиль, привязанный к проекту или playbook."}
              </p>
            </section>

            <section className="rounded-lg border border-gray-200 p-4">
              <h4 className="text-sm font-semibold text-gray-900">
                Основной язык анализа
              </h4>

              <div className="mt-3 flex items-center gap-2">
                <select
                  className="rounded border px-2 py-1 text-xs bg-white text-gray-700 disabled:opacity-50"
                  value={selectedPrimaryLanguage}
                  onChange={(e) => onPrimaryLanguageChange(e.target.value)}
                  disabled={documentLanguages.length === 0 || isSubmitting}
                >
                  <option value="">
                    {hasMultipleDocumentLanguages
                      ? "Выберите основной язык"
                      : "Авто (единственный язык сделки)"}
                  </option>
                  {documentLanguages.map((lang) => (
                    <option key={lang} value={lang}>
                      {lang}
                    </option>
                  ))}
                </select>

                {isSubmitting && (
                  <span className="text-[11px] text-gray-400">Сохраняем…</span>
                )}
              </div>

              {documentLanguages.length > 0 && (
                <p className="mt-2 text-xs text-gray-500">
                  Языки документов: {documentLanguages.join(", ")}
                </p>
              )}

              {hasMultipleDocumentLanguages && !selectedPrimaryLanguage && (
                <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
                  В сделке есть документы на нескольких языках. Перед запуском анализа
                  выберите основной язык, на нём будут выполняться нормализация,
                  извлечение данных и оценка рисков.
                </p>
              )}
            </section>

            {deal.has_pending_manual_reclassifications && (
              <section className="rounded-lg border border-gray-200 p-4">
                <h4 className="text-sm font-semibold text-gray-900">
                  Дополнительные параметры
                </h4>

                <label className="mt-3 flex items-start gap-2 text-xs text-gray-700">
                  <input
                    type="checkbox"
                    className="mt-[2px]"
                    checked={forceReclassify}
                    onChange={(e) => onForceReclassifyChange(e.target.checked)}
                    disabled={isSubmitting}
                  />
                  <span>
                    <span className="block text-[13px] font-medium text-gray-900">
                      Принудительно переклассифицировать документы
                    </span>
                    <span className="block text-[11px] text-gray-500">
                      Используйте после ручной переклассификации, чтобы обновить типы документов.
                    </span>
                  </span>
                </label>
              </section>
            )}
          </div>

          <div className="flex items-center justify-between border-t border-gray-200 px-5 py-4">
            <Button variant="secondary" size="sm" onClick={onClose}>
              Отмена
            </Button>

            <div className="flex items-center gap-3">
              {!canLaunchRun && (
                <span className="text-[11px] text-gray-500">
                  {readinessLabel}
                </span>
              )}
              <Button
                variant="primary"
                size="sm"
                onClick={onSubmit}
                disabled={!canLaunchRun}
                isLoading={isSubmitting}
              >
                Запустить анализ
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div
        className="fixed inset-0 z-40 bg-black/20 xl:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="fixed inset-x-4 top-20 bottom-4 z-50 flex flex-col rounded-lg border border-gray-200 bg-white shadow-xl xl:hidden">
        <div className="flex items-start justify-between border-b border-gray-200 px-4 py-4">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              Запуск анализа
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              Проверьте параметры анализа для этой сделки.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            aria-label="Закрыть панель запуска"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto p-4">
          <section className="rounded-lg border border-gray-200 p-4">
            <div className="flex flex-col gap-3">
              <div>
                <h4 className="text-sm font-semibold text-gray-900">
                  Документы
                </h4>
                <p className="mt-1 text-xs text-gray-600">
                  {typeof documentsCount === "number"
                    ? `В проект загружено ${documentsCount} документ(ов).`
                    : "Загружаем информацию о документах…"}
                </p>
                <p className="mt-1 text-[11px] text-gray-500">
                  Для добавления новых документов используйте отдельный сценарий загрузки.
                </p>
              </div>

              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenUpload}
                disabled={!canUploadDocuments}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                Загрузить дополнительные документы
              </Button>
            </div>
          </section>
        </div>
      </div>
    </>
  );
};

const AnalysisActionsPanel: React.FC<{
  deal: Deal;
  latestRunExists: boolean;
  canStartRun: boolean;
  onOpenRunPanel: () => void;
  showReclassBanner: boolean;
}> = ({
  deal,
  latestRunExists,
  canStartRun,
  onOpenRunPanel,
  showReclassBanner,
}) => {
  const hasPlaybook = !!deal.playbook_version_id;
  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const primaryLanguageSelected = !!deal.primary_language;

  return (
    <div className="self-start rounded-lg border bg-white p-5 xl:sticky xl:top-6">
      <div className="flex h-full flex-col">
        <div>
          <h3 className="text-base font-semibold text-gray-900">
            Анализ документов
          </h3>

          {!latestRunExists ? (
            <p className="mt-2 text-sm leading-6 text-gray-600">
              Перед первым запуском система предложит вам последовательно
              выбрать режим проверки, playbook, профиль модели и основной язык анализа.
            </p>
          ) : (
            <p className="mt-2 text-sm leading-6 text-gray-600">
              Вы можете запустить повторный анализ, чтобы обновить результаты
              по текущему набору документов и параметрам проверки.
            </p>
          )}
        </div>

        {showReclassBanner && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-3">
            <p className="text-xs font-semibold text-amber-900">
              Требуется обновление результатов
            </p>
            <p className="mt-1 text-xs leading-5 text-amber-800">
              После ручной переклассификации рекомендуется повторно запустить
              анализ, чтобы привести выводы, DD Grid и связанные результаты в
              актуальное состояние.
            </p>
          </div>
        )}

        {!latestRunExists && (
          <div className="mt-5 rounded-md bg-gray-50 px-4 py-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-700">
              Что потребуется выбрать
            </p>

            <div className="mt-3 space-y-3">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  1. Режим проверки
                </p>
                <p className="mt-1 text-xs leading-5 text-gray-600">
                  Определяет, как будет выполняться анализ: по playbook, по
                  типам документов или в комбинированном режиме.
                </p>
              </div>

              <div>
                <p className="text-sm font-medium text-gray-900">
                  2. Playbook проверки
                </p>
                <p className="mt-1 text-xs leading-5 text-gray-600">
                  Набор рисков, вопросов и критериев, которые система будет
                  оценивать в проверяемых документах.
                </p>
              </div>

              <div>
                <p className="text-sm font-medium text-gray-900">
                  3. Профиль модели проверки
                </p>
                <p className="mt-1 text-xs leading-5 text-gray-600">
                  Позволяет выбрать приоритет анализа: быстро, стандартно или
                  качественно.
                </p>
              </div>

              <div>
                <p className="text-sm font-medium text-gray-900">
                  4. Основной язык анализа
                </p>
                <p className="mt-1 text-xs leading-5 text-gray-600">
                  Нужен для корректной обработки документов, особенно если в
                  проекте несколько языков.
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="mt-5 rounded-md border border-gray-200 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-700">
            Текущая готовность
          </p>

          <div className="mt-3 space-y-2">
            <StatusRow
              label="Playbook проекта"
              value={hasPlaybook ? "Выбран" : "Не выбран"}
              tone={hasPlaybook ? "ok" : "warn"}
            />

            <StatusRow
              label="Языки документов"
              value={
                documentLanguages.length > 0
                  ? documentLanguages.join(", ")
                  : "Ещё не определены"
              }
              tone={documentLanguages.length > 0 ? "ok" : "neutral"}
            />

            <StatusRow
              label="Основной язык анализа"
              value={
                deal.primary_language
                  ? deal.primary_language
                  : hasMultipleDocumentLanguages
                  ? "Нужно выбрать перед запуском"
                  : "Будет определён автоматически"
              }
              tone={
                primaryLanguageSelected
                  ? "ok"
                  : hasMultipleDocumentLanguages
                  ? "warn"
                  : "neutral"
              }
            />

            <StatusRow
              label="Профиль модели"
              value={deal.model_config_name || "Будет использован профиль проекта"}
              tone={deal.model_config_name ? "ok" : "neutral"}
            />
          </div>
        </div>

        <div className="mt-5">
          <Button
            variant="primary"
            size="sm"
            onClick={onOpenRunPanel}
            disabled={!canStartRun}
          >
            Запустить анализ документов
          </Button>
        </div>
      </div>
    </div>
  );
};

const OverviewTab: React.FC<OverviewTabProps> = ({
  deal,
  latestRunId,
  onOpenModelConfig,
}) => {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: latestRun } = useRun(latestRunId ?? null, false);
  const { data: documentsCount } = useDocumentsCount(deal.id);

  const { canStartRun, canUploadDocuments } = useDealPermissions(deal.id);

  const startRun = useStartRun(deal.id);
  const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);

  const [isLaunchPanelOpen, setIsLaunchPanelOpen] = React.useState(false);
  const [checksMode, setChecksMode] =
    React.useState<ChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [hasRestartedAfterReclass, setHasRestartedAfterReclass] =
    React.useState(false);

  const readableChecksMode =
    latestRun?.checks_mode === "global_and_doc_type"
      ? "Плейбук + типы документов"
      : latestRun?.checks_mode === "global_only"
      ? "Только плейбук"
      : latestRun?.checks_mode === "doc_type_only"
      ? "Только типы документов"
      : null;

  const showReclassBanner =
    deal.has_pending_manual_reclassifications &&
    (!!latestRun || !hasRestartedAfterReclass);

  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const selectedPrimaryLanguage = deal.primary_language ?? "";

  const requiresExplicitPrimaryLanguage = hasMultipleDocumentLanguages;
  const hasValidPrimaryLanguageSelection =
    !requiresExplicitPrimaryLanguage || !!selectedPrimaryLanguage;
  const hasPlaybook = !!deal.playbook_version_id;

  const canLaunchRun =
    canStartRun &&
    hasPlaybook &&
    hasValidPrimaryLanguageSelection &&
    !startRun.isPending &&
    !setPrimaryLanguage.isPending;

  const handleOpenPlaybook = () => {
    navigate(`/projects/${deal.id}/playbook`);
  };

  const handleOpenUpload = () => {
    if (!canUploadDocuments) return;
    navigate(`/projects/${deal.id}/upload`);
  };

  const handlePrimaryLanguageChange = (value: string) => {
    const normalizedValue = value || null;

    setPrimaryLanguage.mutate(
      { primary_language: normalizedValue },
      {
        onSuccess: async () => {
          await Promise.all([
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, true] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, false] }),
          ]);
        },
      },
    );
  };

  const handleStartRun = () => {
    if (!canLaunchRun) {
      return;
    }

    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: async (run) => {
          setHasRestartedAfterReclass(true);
          setForceReclassify(false);
          setIsLaunchPanelOpen(false);

          await Promise.all([
            qc.invalidateQueries({ queryKey: ["run", run.id, true] }),
            qc.invalidateQueries({ queryKey: ["run", run.id, false] }),
            qc.invalidateQueries({
              queryKey: ["classification-report", run.id],
            }),
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, true] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, false] }),
          ]);
        },
      },
    );
  };

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsLaunchPanelOpen(false);
      }
    };

    if (isLaunchPanelOpen) {
      window.addEventListener("keydown", onKeyDown);
    }

    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isLaunchPanelOpen]);

  return (
    <div className="relative grid gap-4 xl:grid-cols-[minmax(0,2.2fr)_minmax(320px,1fr)]">
      <div className="relative space-y-4">
        <div className="rounded-lg border bg-white p-5">
          <div>
            <h2 className="mb-1 text-xl font-bold text-gray-900">
              Обзор сделки
            </h2>
            <p className="text-sm text-gray-600">
              {deal.name} · статус: {deal.status}
            </p>

            {latestRun && (
              <p className="mt-1 text-xs text-gray-500">
                Последний анализ:{" "}
                {readableChecksMode && (
                  <>
                    режим{" "}
                    <span className="font-medium text-gray-700">
                      {readableChecksMode}
                    </span>
                  </>
                )}
                {latestRun.pipeline_strategy && (
                  <>
                    {readableChecksMode && " · "}
                    стратегия{" "}
                    <span className="font-medium text-gray-700">
                      {latestRun.pipeline_strategy}
                    </span>
                  </>
                )}
              </p>
            )}
          </div>

          <div className="mt-4 border-t border-gray-100 pt-4">
            <div className="flex flex-col gap-1 text-xs text-gray-600">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <span className="font-semibold">Playbook проекта:</span>{" "}
                  {deal.playbook_version_id ? (
                    <span>выбран</span>
                  ) : (
                    <span className="text-gray-500">не выбран</span>
                  )}
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleOpenPlaybook}
                >
                  Открыть playbook
                </Button>
              </div>

              <div className="flex items-center justify-between gap-4 text-gray-600">
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
                  <Button
                    variant="secondary"
                    size="md"
                    onClick={onOpenModelConfig}
                  >
                    Настроить профиль модели
                  </Button>
                )}
              </div>

              <div className="mt-2 flex flex-col gap-1 text-xs text-gray-600">
                <div>
                  <span className="font-semibold">Языки документов:</span>{" "}
                  {documentLanguages.length > 0 ? (
                    <span>{documentLanguages.join(", ")}</span>
                  ) : (
                    <span className="text-gray-500">ещё не определены</span>
                  )}
                </div>

                <div>
                  <span className="font-semibold">Основной язык анализа:</span>{" "}
                  {deal.primary_language ? (
                    <span>{deal.primary_language}</span>
                  ) : hasMultipleDocumentLanguages ? (
                    <span className="text-red-600">
                      не выбран (нужно выбрать перед запуском анализа)
                    </span>
                  ) : (
                    <span className="text-gray-500">
                      будет определён автоматически
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        <RunProgressCard latestRunId={latestRunId} />
        <ClassificationQualityCard dealId={deal.id} latestRunId={latestRunId} />
      </div>

      <div className="relative">
        <AnalysisActionsPanel
          deal={deal}
          latestRunExists={!!latestRun}
          canStartRun={canStartRun}
          onOpenRunPanel={() => setIsLaunchPanelOpen(true)}
          showReclassBanner={showReclassBanner}
        />

        <LaunchOverlayPanel
          open={isLaunchPanelOpen}
          onClose={() => setIsLaunchPanelOpen(false)}
          deal={deal}
          latestRunId={latestRunId}
          documentsCount={documentsCount}
          checksMode={checksMode}
          onChecksModeChange={setChecksMode}
          forceReclassify={forceReclassify}
          onForceReclassifyChange={setForceReclassify}
          canStartRun={canStartRun}
          canUploadDocuments={canUploadDocuments}
          isSubmitting={startRun.isPending || setPrimaryLanguage.isPending}
          onOpenPlaybook={handleOpenPlaybook}
          onOpenModelConfig={onOpenModelConfig}
          onOpenUpload={handleOpenUpload}
          onPrimaryLanguageChange={handlePrimaryLanguageChange}
          onSubmit={handleStartRun}
        />
      </div>
    </div>
  );
};

export default OverviewTab;





