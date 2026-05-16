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
  currentRunId?: string | null;
  documentsCount?: number;

  checksMode: ChecksMode;
  onChecksModeChange: (value: ChecksMode) => void;

  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;

  canStartRun: boolean;
  canUploadDocuments: boolean;
  canLaunchRun: boolean;
  isSubmitting: boolean;

  onOpenPlaybook: () => void;
  onOpenModelConfig?: () => void;
  onOpenUpload: () => void;
  onPrimaryLanguageChange: (value: string) => void;
  onSubmit: () => void;
}

const SECONDARY_ACTION_BUTTON_CLASS =
  "w-[220px] shrink-0 justify-center whitespace-nowrap text-sm font-semibold";

const RunLaunchDrawer: React.FC<RunLaunchDrawerProps> = ({
  open,
  onClose,
  deal,
  currentRunId,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canStartRun,
  canUploadDocuments,
  canLaunchRun,
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
  const hasPlaybook = !!deal.playbook_version_id;

  const readinessLabel = !hasPlaybook
    ? "Нужно выбрать playbook, чтобы запустить анализ."
    : hasMultipleDocumentLanguages && !selectedPrimaryLanguage
      ? "Нужно выбрать основной язык анализа."
      : "Параметры готовы к запуску анализа.";

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
              variant="secondary"
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
      <div className="space-y-4">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
          <p className="text-xs font-semibold text-[var(--text-primary)]">
            {readinessLabel}
          </p>
          {currentRunId && (
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
              Последний анализ уже запускался. Новый запуск обновит результаты по
              текущим документам.
            </p>
          )}
        </div>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                Документы
              </h4>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                {typeof documentsCount === "number"
                  ? `В проект загружено ${documentsCount} документ(ов).`
                  : "Загружаем информацию о документах…"}
              </p>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                Для добавления новых документов используйте отдельный сценарий
                загрузки.
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

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            Режим проверки
          </h4>
          <div className="mt-3 space-y-2">
            {(
              [
                {
                  value: "global_and_doc_type",
                  title: "Playbook и типы документов",
                  hint: "Рекомендуемый режим: комбинирует глобальный playbook и типовые проверки.",
                },
                {
                  value: "global_only",
                  title: "Только Playbook",
                  hint: "Анализ только по правилам playbook без привязки к типу документа.",
                },
                {
                  value: "doc_type_only",
                  title: "Только типы документов",
                  hint: "Используются проверки, привязанные к типам документов.",
                },
              ] as { value: ChecksMode; title: string; hint: string }[]
            ).map(({ value, title, hint }) => (
              <label
                key={value}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 transition ${
                  checksMode === value
                    ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                    : "border-[var(--border-soft)] bg-[var(--bg-card)] hover:bg-[var(--bg-elevated-soft)]"
                }`}
              >
                <input
                  type="radio"
                  className="mt-[2px]"
                  value={value}
                  checked={checksMode === value}
                  onChange={() => onChecksModeChange(value)}
                  disabled={isSubmitting || !canStartRun}
                />
                <span>
                  <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                    {title}
                  </span>
                  <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                    {hint}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                Playbook проекта
              </h4>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
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
          <p className="mt-3 text-xs leading-5">
            {hasPlaybook ? (
              <span className="text-[var(--text-secondary)]">
                Playbook выбран. При необходимости вы можете изменить его перед
                запуском.
              </span>
            ) : (
              <span className="text-rose-600">
                Playbook не выбран. Нельзя запустить анализ без выбранного
                playbook.
              </span>
            )}
          </p>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                Профиль модели
              </h4>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
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
          <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
            {deal.model_config_name
              ? `Текущий профиль: ${deal.model_config_name}.`
              : "Будет использован профиль, привязанный к проекту или playbook."}
          </p>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            Основной язык анализа
          </h4>
          <div className="mt-3 flex items-center gap-2">
            <select
              className="min-w-[220px] rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-xs text-[var(--text-primary)] disabled:opacity-50"
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

          {documentLanguages.length > 0 && (
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Языки документов: {documentLanguages.join(", ")}
            </p>
          )}

          {hasMultipleDocumentLanguages && !selectedPrimaryLanguage && (
            <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
              В сделке есть документы на нескольких языках. Перед запуском анализа
              выберите основной язык.
            </p>
          )}
        </section>

        {deal.has_pending_manual_reclassifications && (
          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">
              Дополнительные параметры
            </h4>
            <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-card)] px-3 py-3 text-xs text-[var(--text-secondary)]">
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
                <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                  Используйте после ручной переклассификации, чтобы обновить типы
                  документов.
                </span>
              </span>
            </label>
          </section>
        )}
      </div>
    </Drawer>
  );
};

export default RunLaunchDrawer;

