// =============================================================
// src/components/new-project/FlowBlock.tsx
//
// Обёртка одного шага в flow запуска нового проекта.
//
// Три состояния:
//   disabled — блок ещё недоступен (opacity + no interaction)
//   active   — текущий активный шаг (accent-полоска слева)
//   done     — шаг завершён (галочка, контент сворачивается)
//
// Не содержит бизнес-логики — только визуальная оболочка.
// =============================================================

import React from "react";

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
   * Показывается под заголовком когда блок свёрнут.
   */
  summary?: string;
  /** Контент блока (форма, список, и т.д.) */
  children: React.ReactNode;
}

const FlowBlock: React.FC<FlowBlockProps> = ({
  step,
  title,
  status,
  summary,
  children,
}) => {
  const [isExpanded, setIsExpanded] = React.useState(false);

  // Сбрасываем expanded когда блок становится active или disabled
  React.useEffect(() => {
    if (status !== "done") {
      setIsExpanded(false);
    }
  }, [status]);

  const isDone = status === "done";
  const isDisabled = status === "disabled";
  const isActive = status === "active";

  // Done-блок можно раскрыть/свернуть кликом на header
  const handleHeaderClick = () => {
    if (isDone) {
      setIsExpanded((prev) => !prev);
    }
  };

  const showContent = isActive || (isDone && isExpanded);

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

      {/* Header */}
      <div
        className={[
          "flex items-center gap-4 px-5 py-4",
          isDone
            ? "cursor-pointer select-none hover:bg-[var(--bg-elevated-soft)] rounded-2xl transition-colors"
            : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={handleHeaderClick}
        role={isDone ? "button" : undefined}
        tabIndex={isDone ? 0 : undefined}
        aria-expanded={isDone ? isExpanded : undefined}
        onKeyDown={
          isDone
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setIsExpanded((prev) => !prev);
                }
              }
            : undefined
        }
      >
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
            // Checkmark SVG
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

        {/* Title + summary */}
        <div className="min-w-0 flex-1">
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

          {isDone && summary && !isExpanded && (
            <p className="mt-0.5 truncate text-[11px] text-[var(--text-secondary)]">
              {summary}
            </p>
          )}
        </div>

        {/* Done — chevron indicator */}
        {isDone && (
          <span
            className={[
              "shrink-0 text-[var(--text-muted)] transition-transform duration-200",
              isExpanded ? "rotate-180" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-hidden="true"
          >
            <svg
              viewBox="0 0 12 12"
              fill="none"
              className="h-3 w-3"
              aria-hidden="true"
            >
              <path
                d="M2 4l4 4 4-4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        )}
      </div>

      {/* Content */}
      {showContent && (
        <>
          <div className="mx-5 border-t border-[var(--border-subtle)]" />
          <div
            className={[
              "px-5 py-5",
              isDisabled ? "pointer-events-none" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {children}
          </div>
        </>
      )}
    </div>
  );
};

export default FlowBlock;



