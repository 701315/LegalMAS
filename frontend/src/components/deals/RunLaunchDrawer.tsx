// src/components/deals/RunLaunchDrawer.tsx

import React from "react";
import type { Deal } from "../../types/deals";
import Drawer from "../ui/Drawer";
import Button from "../ui/Button";

type ChecksMode = "global_only" | "doc_type_only" | "global_and_doc_type";

interface RunLaunchDrawerProps {
  open: boolean;
  onClose: () => void;
  deal: Deal;
  latestRunId?: string | null;

  checksMode: ChecksMode;
  onChecksModeChange: (value: ChecksMode) => void;

  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;

  canStartRun: boolean;
  isSubmitting: boolean;

  onOpenPlaybook: () => void;
  onOpenModelConfig?: () => void;
  onPrimaryLanguageChange: (value: string) => void;
  onSubmit: () => void;
}

const RunLaunchDrawer: React.FC<RunLaunchDrawerProps> = ({
  open,
  onClose,
  deal,
  latestRunId,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canStartRun,
  isSubmitting,
  onOpenPlaybook,
  onOpenModelConfig,
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
    canStartRun &&
    hasPlaybook &&
    hasValidPrimaryLanguageSelection &&
    !isSubmitting;

  let readinessLabel: string;
  if (!hasPlaybook) {
    readinessLabel = "Нужно выбрать Playbook, чтобы запустить анализ.";
  } else if (!hasValidPrimaryLanguageSelection) {
    readinessLabel = "Нужно выбрать основной язык анализа.";
  } else {
    readinessLabel = "Готово к запуску анализа.";
  }

  const handleSubmit = () => {
    if (!canLaunchRun) return;
    onSubmit();
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Запуск анализа"
      description="Проверьте параметры анализа для этой сделки."
      footer={
        <div className="flex items-center justify-between gap-3">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Отмена
          </Button>

          <div className="flex items-center gap-3">
            {!canLaunchRun && (
              <span className="text-[11px] text-[var(--text-muted)]">
                {readinessLabel}
              </span>
            )}
            <Button
              variant="primary"
              size="sm"
              onClick={handleSubmit}
              disabled={!canLaunchRun}
              isLoading={isSubmitting}
            >
              Запустить анализ
            </Button>
          </div>
        </div>
      }
    >
      {/* Readiness summary */}
      <div className="mb-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2">
        <p className="text-xs font-semibold text-[var(--text-primary)]">
          {readinessLabel}
        </p>
        {latestRunId && (
          <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">
            Последний анализ уже запускался. Новый запуск обновит результаты по
            текущим документам.
          </p>
        )}
      </div>

      {/* Documents & languages */}
      <section className="mb-4 space-y-1 text-xs text-[var(--text-secondary)]">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Документы
        </h3>
        <p>
          Языки документов:{" "}
          {documentLanguages.length > 0
            ? documentLanguages.join(", ")
            : "ещё не определены (анализ не запускался)"}
        </p>
      </section>

      {/* Playbook */}
      <section className="mb-4 space-y-1 text-xs text-[var(--text-secondary)]">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              Playbook проекта
            </h3>
            <p className="text-[11px] text-[var(--text-muted)]">
              Используется для формирования проверок и DD Grid.
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={onOpenPlaybook}>
            Открыть Playbook
          </Button>
        </div>
        <p className="text-xs">
          {hasPlaybook ? (
            <span className="text-[var(--text-secondary)]">
              Playbook выбран. При необходимости вы можете изменить его перед
              запуском.
            </span>
          ) : (
            <span className="text-[var(--color-error)]">
              Playbook не выбран. Нельзя запустить анализ без выбранного
              playbook.
            </span>
          )}
        </p>
      </section>

      {/* Primary language */}
      <section className="mb-4 space-y-2 text-xs text-[var(--text-secondary)]">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Основной язык анализа
        </h3>

        <div className="flex items-center gap-2">
          <select
            className="rounded border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)] disabled:opacity-50"
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
            <span className="text-[11px] text-[var(--text-muted)]">
              Сохраняем…
            </span>
          )}
        </div>

        {hasMultipleDocumentLanguages && !selectedPrimaryLanguage && (
          <p className="rounded-2xl border border-[var(--color-warning-highlight)] bg-[var(--color-warning-highlight)]/40 px-3 py-2 text-[11px] text-[var(--color-warning)]">
            В сделке есть документы на нескольких языках. Перед запуском анализа
            выберите основной язык, на нём будут выполняться нормализация,
            извлечение данных и оценка рисков.
          </p>
        )}
      </section>

      {/* Checks mode */}
      <section className="mb-4 space-y-2 text-xs text-[var(--text-secondary)]">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Режим проверки
        </h3>
        <div className="space-y-1.5">
          <label className="flex items-start gap-2">
            <input
              type="radio"
              className="mt-[2px]"
              value="global_and_doc_type"
              checked={checksMode === "global_and_doc_type"}
              onChange={() => onChecksModeChange("global_and_doc_type")}
              disabled={isSubmitting || !canStartRun}
            />
            <span>
              <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                Playbook и типы документов
              </span>
              <span className="block text-[11px] text-[var(--text-muted)]">
                Рекомендуемый режим: комбинирует глобальный playbook и типовые
                проверки.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              className="mt-[2px]"
              value="global_only"
              checked={checksMode === "global_only"}
              onChange={() => onChecksModeChange("global_only")}
              disabled={isSubmitting || !canStartRun}
            />
            <span>
              <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                Только Playbook
              </span>
              <span className="block text-[11px] text-[var(--text-muted)]">
                Анализ только по правилам playbook без привязки к типу документа.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              className="mt-[2px]"
              value="doc_type_only"
              checked={checksMode === "doc_type_only"}
              onChange={() => onChecksModeChange("doc_type_only")}
              disabled={isSubmitting || !canStartRun}
            />
            <span>
              <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                Только типы документов
              </span>
              <span className="block text-[11px] text-[var(--text-muted)]">
                Используются проверки, привязанные к типам документов.
              </span>
            </span>
          </label>
        </div>
      </section>

      {/* Additional */}
      {deal.has_pending_manual_reclassifications && (
        <section className="mt-4 border-t border-[var(--border-subtle)] pt-4">
          <p className="mb-2 text-xs font-semibold text-[var(--text-primary)]">
            Дополнительные параметры
          </p>

          <label className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
            <input
              type="checkbox"
              className="mt-[2px]"
              checked={forceReclassify}
              onChange={(e) => onForceReclassifyChange(e.target.checked)}
              disabled={isSubmitting}
            />
            <span>
              <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                Принудительно переклассифицировать документы
              </span>
              <span className="block text-[11px] text-[var(--text-muted)]">
                Используйте после ручной переклассификации, чтобы обновить типы
                документов.
              </span>
            </span>
          </label>

          {onOpenModelConfig && deal.model_config_name && (
            <div className="mt-3 flex items-center justify-between text-xs text-[var(--text-secondary)]">
              <div>
                <span className="font-semibold text-[var(--text-primary)]">
                  Профиль модели:{" "}
                </span>
                <span>{deal.model_config_name}</span>
              </div>
              <Button variant="secondary" size="sm" onClick={onOpenModelConfig}>
                Настроить модель
              </Button>
            </div>
          )}
        </section>
      )}
    </Drawer>
  );
};

export default RunLaunchDrawer;

