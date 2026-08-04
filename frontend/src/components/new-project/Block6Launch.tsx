// =============================================================
// src/components/new-project/Block6Launch.tsx
//
// Блок 6 — Режим проверки + кнопка «Запустить проект».
//
// Содержит:
//   - radio-выбор режима проверки (3 варианта)
//   - checkbox force reclassify (если применимо)
//   - кнопка «Запустить проект»
//
// Не содержит API-логики — все callbacks передаются сверху.
// =============================================================

import React from "react";
import { Rocket } from "lucide-react";

import type { RunChecksMode } from "../../types";

import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";

interface Block6LaunchProps {
  checksMode: RunChecksMode;
  onChecksModeChange: (value: RunChecksMode) => void;
  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;
  /** Показывать ли опцию force reclassify */
  showForceReclassify: boolean;
  /** Все обязательные условия для запуска выполнены */
  canLaunch: boolean;
  isSubmitting: boolean;
  errorText?: string | null;
  onLaunch: () => void;
}

const CHECKS_MODE_OPTIONS: Array<{
  value: RunChecksMode;
  title: string;
  hint: string;
}> = [
  {
    value: "global_and_doc_type",
    title: "Playbook и типы документов",
    hint: "Рекомендуемый режим. Включает все проверки playbook и проверки по типам документов.",
  },
  {
    value: "global_only",
    title: "Только Playbook",
    hint: "Только правила playbook. Проверки по типам документов не выполняются.",
  },
  {
    value: "doc_type_only",
    title: "Только типы документов",
    hint: "Только проверки по типам документов. Правила playbook не применяются.",
  },
];

const Block6Launch: React.FC<Block6LaunchProps> = ({
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  showForceReclassify,
  canLaunch,
  isSubmitting,
  errorText = null,
  onLaunch,
}) => {
  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();

    if (!canLaunch || isSubmitting) {
      return;
    }

    onLaunch();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {errorText ? <InlineAlert tone="error" message={errorText} /> : null}

      {/* ── Режим проверки ─────────────────────────────────── */}
      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Режим проверки
        </p>

        <p className="mb-3 text-[11px] leading-5 text-[var(--text-secondary)]">
          Выберите набор проверок для запуска анализа.
        </p>

        <div className="space-y-2">
          {CHECKS_MODE_OPTIONS.map(({ value, title, hint }) => {
            const isChecked = checksMode === value;

            return (
              <label
                key={value}
                className={[
                  "flex items-start gap-3 rounded-xl border px-3 py-3 transition",
                  isChecked
                    ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                    : "border-[var(--border-subtle)] bg-[var(--bg-card)]",
                  isSubmitting
                    ? "cursor-not-allowed opacity-70"
                    : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-disabled={isSubmitting}
              >
                <input
                  type="radio"
                  name="new_project_checks_mode"
                  className="mt-[2px]"
                  value={value}
                  checked={isChecked}
                  onChange={() => onChecksModeChange(value)}
                  disabled={isSubmitting}
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
            );
          })}
        </div>
      </div>

      {/* ── Force reclassify ───────────────────────────────── */}
      {showForceReclassify ? (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Дополнительные параметры
          </p>

          <label
            className={[
              "flex items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3 transition",
              isSubmitting
                ? "cursor-not-allowed opacity-70"
                : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-disabled={isSubmitting}
          >
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
                Используйте после ручной переклассификации документов.
              </span>
            </span>
          </label>
        </div>
      ) : null}

      {/* ── Launch button ──────────────────────────────────── */}
      <div className="border-t border-[var(--border-subtle)] pt-4">
        <div className="subtle-panel px-4 py-3">
          <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
            После запуска система начнёт обработку всех загруженных документов
            в соответствии с выбранными настройками. Вы будете перенаправлены
            на страницу проекта для отслеживания прогресса.
          </p>
        </div>

        <div className="mt-4 flex justify-end">
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!canLaunch || isSubmitting}
            isLoading={isSubmitting}
            leftIcon={
              !isSubmitting ? (
                <Rocket className="h-3.5 w-3.5" />
              ) : undefined
            }
          >
            {isSubmitting ? "Запускаем анализ…" : "Запустить проект"}
          </Button>
        </div>
      </div>
    </form>
  );
};

export default Block6Launch;


