// =============================================================
// src/components/new-project/FlowBlock.tsx
//
// Обёртка одного шага в flow запуска нового проекта.
//
// Три состояния:
//   disabled — блок ещё недоступен (opacity + no interaction)
//   active   — текущий активный шаг (accent-полоска слева)
//              + опциональная кнопка «Назад к шагу N» в шапке
//   done     — шаг завершён; свёрнут в одну строку с чекмарком,
//              summary и кнопкой «карандаш» для редактирования
//
// Не содержит бизнес-логики — только визуальная оболочка.
// =============================================================

import React from "react";
import { ArrowLeft, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

export type FlowBlockStatus = "disabled" | "active" | "done";

interface FlowBlockProps {
  /** Порядковый номер шага для отображения */
  step: number;
  /** Заголовок блока */
  title: string;
  /** Состояние блока */
  status: FlowBlockStatus;
  /**
   * Краткое summary для done-состояния.
   * Показывается справа от заголовка в одной строке.
   */
  summary?: string;
  /** Контент блока (форма, список, и т.д.) */
  children: React.ReactNode;

  /**
   * Обработчик клика по кнопке «Назад к шагу N» в шапке active-блока.
   * Если не задан — кнопка не показывается.
   */
  onBackRequest?: () => void;
  /**
   * Подпись кнопки «Назад». Например: "Назад к шагу 3".
   * Обязателен если задан onBackRequest.
   */
  backLabel?: string;

  /**
   * Обработчик клика по кнопке "карандаш" в done-блоке.
   * Если не задан — кнопка не показывается.
   */
  onEditRequest?: () => void;
}

const FlowBlock: React.FC<FlowBlockProps> = ({
  step,
  title,
  status,
  summary,
  children,
  onBackRequest,
  backLabel,
  onEditRequest,
}) => {
  const { t } = useTranslation("projects");

  const isDone = status === "done";
  const isDisabled = status === "disabled";
  const isActive = status === "active";

  const showContent = isActive;

  return (
    <div
      className={[
        "relative rounded-2xl border bg-[var(--bg-card)] shadow-sm transition-opacity duration-200",
        isDisabled
          ? "border-[var(--border)] opacity-50"
          : isActive
            ? "border-[var(--accent-primary)]/40"
            : "border-[var(--border)]",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-disabled={isDisabled}
    >
      {/* Accent-полоска слева — только для active */}
      {isActive && (
        <div
          className="absolute left-0 top-4 bottom-4 w-[3px] rounded-full bg-[var(--accent-primary)]"
          aria-hidden="true"
        />
      )}

      {/* ── Кнопка "Назад" в шапке active-блока ──────────── */}
      {isActive && onBackRequest && backLabel ? (
        <div className="border-b border-[var(--border-subtle)] px-5 pb-2 pt-3">
          <button
            type="button"
            onClick={onBackRequest}
            className="inline-flex items-center gap-1.5 rounded-md text-[11px] font-medium text-[var(--text-muted)] transition-colors hover:text-[var(--accent-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          >
            <ArrowLeft className="h-3 w-3" aria-hidden="true" />
            {backLabel}
          </button>
        </div>
      ) : null}

      {/* ── Header ───────────────────────────────────────── */}
      <div className="flex items-center gap-4 px-5 py-4">
        {/* Step indicator */}
        <div
          className={[
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors",
            isDone
              ? "bg-[var(--accent-primary)] text-white"
              : isActive
                ? "border-2 border-[var(--accent-primary)] text-[var(--accent-primary)]"
                : "border border-[var(--border)] text-[var(--text-muted)]",
          ]
            .filter(Boolean)
            .join(" ")}
          aria-hidden="true"
        >
          {isDone ? (
            <svg
              viewBox="0 0 12 12"
              fill="none"
              className="h-3.5 w-3.5"
              aria-hidden="true"
            >
              <path
                d="M2 6l3 3 5-5"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            step
          )}
        </div>

        {/* Title + inline summary для done */}
        <div className="min-w-0 flex-1">
          {isDone && summary ? (
            // Done: title и summary в одну строку с разделителем "·"
            <div className="flex items-center gap-2 min-w-0">
              <h2 className="text-sm font-semibold text-[var(--text-primary)] shrink-0">
                {title}
              </h2>
              <span
                className="shrink-0 text-[var(--text-faint)]"
                aria-hidden="true"
              >
                ·
              </span>
              <p
                className="min-w-0 truncate text-[12px] text-[var(--text-secondary)]"
                title={summary}
              >
                {summary}
              </p>
            </div>
          ) : (
            <h2
              className={[
                "text-sm font-semibold",
                isDisabled
                  ? "text-[var(--text-muted)]"
                  : "text-[var(--text-primary)]",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {title}
            </h2>
          )}
        </div>

        {/* Done — кнопка "карандаш" (редактировать) */}
        {isDone && onEditRequest ? (
          <button
            type="button"
            onClick={onEditRequest}
            aria-label={t("newProject.editStepAria", { title })}
            className="shrink-0 rounded-md p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--accent-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          >
            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        ) : null}
      </div>

      {/* ── Content (только для active) ─────────────────── */}
      {showContent && (
        <>
          <div className="mx-5 border-t border-[var(--border-subtle)]" />
          <div className="px-5 py-5">{children}</div>
        </>
      )}
    </div>
  );
};

export default FlowBlock;

