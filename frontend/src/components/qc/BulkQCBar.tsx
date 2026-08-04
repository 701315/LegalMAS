// =============================================================
// src/components/qc/BulkQCBar.tsx
// =============================================================

import React from "react";
import type { CheckResultValue, SeverityLevel } from "../../types";

interface BulkQCBarProps {
  selectedCount: number;
  onConfirm: (comment: string) => void;
  onReject: (comment: string) => void;
  onOverride?: (params: {
    newSeverity: SeverityLevel;
    newResult?: CheckResultValue;
    comment: string;
  }) => void;
}

const SEVERITY_OPTIONS: { value: SeverityLevel; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "pass", label: "Pass" },
  { value: "unclear", label: "Unclear" },
];

const RESULT_OPTIONS: { value: CheckResultValue | ""; label: string }[] = [
  { value: "", label: "Не менять result" },
  { value: "pass", label: "Pass" },
  { value: "fail", label: "Fail" },
  { value: "unclear", label: "Unclear" },
];

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export const BulkQCBar: React.FC<BulkQCBarProps> = ({
  selectedCount,
  onConfirm,
  onReject,
  onOverride,
}) => {
  const [comment, setComment] = React.useState("");
  const [showOverride, setShowOverride] = React.useState(false);
  const [newSeverity, setNewSeverity] = React.useState<SeverityLevel>("medium");
  const [newResult, setNewResult] = React.useState<CheckResultValue | "">("");

  const disabled = selectedCount === 0;

  const handleConfirm = () => {
    if (disabled) return;
    onConfirm(comment.trim());
    setComment("");
  };

  const handleReject = () => {
    if (disabled) return;
    onReject(comment.trim());
    setComment("");
  };

  const handleOverride = () => {
    if (disabled || !onOverride) return;
    onOverride({
      newSeverity,
      newResult: newResult !== "" ? newResult : undefined,
      comment: comment.trim(),
    });
    setComment("");
    setShowOverride(false);
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-[var(--border)] bg-[var(--bg-card)] px-4 py-2 text-xs text-[var(--text-secondary)] shadow-lg backdrop-blur">
      {/* Основная строка */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="text-[var(--text-secondary)]">
            Выбрано результатов:{" "}
          </span>
          <span className="font-semibold text-[var(--text-primary)]">
            {selectedCount}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Комментарий QC (опционально)…"
            className="w-64 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          />

          <button
            type="button"
            className={cn(
              "rounded-lg border px-3 py-1 text-xs font-medium transition",
              "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
              "hover:opacity-90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
              "disabled:cursor-not-allowed disabled:opacity-45",
            )}
            onClick={handleConfirm}
            disabled={disabled}
          >
            Подтвердить
          </button>

          <button
            type="button"
            className={cn(
              "rounded-lg border px-3 py-1 text-xs font-medium transition",
              "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
              "hover:opacity-90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
              "disabled:cursor-not-allowed disabled:opacity-45",
            )}
            onClick={handleReject}
            disabled={disabled}
          >
            Отклонить
          </button>

          {onOverride && (
            <button
              type="button"
              className={cn(
                "rounded-lg border px-3 py-1 text-xs font-medium transition",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
                "disabled:cursor-not-allowed disabled:opacity-45",
                showOverride
                  ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]",
              )}
              onClick={() => setShowOverride((v) => !v)}
              disabled={disabled}
            >
              Override…
            </button>
          )}
        </div>
      </div>

      {/* Секция Override */}
      {showOverride && onOverride && (
        <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-[var(--border-soft)] pt-2">
          <span className="text-[var(--text-secondary)]">Override:</span>

          {/* Severity */}
          <div className="flex items-center gap-1">
            <label className="text-[var(--text-secondary)]">Severity:</label>
            <select
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              value={newSeverity}
              onChange={(e) =>
                setNewSeverity(e.target.value as SeverityLevel)
              }
            >
              {SEVERITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Result */}
          <div className="flex items-center gap-1">
            <label className="text-[var(--text-secondary)]">Result:</label>
            <select
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              value={newResult}
              onChange={(e) =>
                setNewResult(e.target.value as CheckResultValue | "")
              }
            >
              {RESULT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            className={cn(
              "rounded-lg border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-1 text-xs font-medium text-[var(--color-warning-text)] transition hover:opacity-90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
              "disabled:cursor-not-allowed disabled:opacity-45",
            )}
            onClick={handleOverride}
            disabled={disabled}
          >
            Применить override
          </button>

          <button
            type="button"
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
            onClick={() => setShowOverride(false)}
          >
            Отмена
          </button>
        </div>
      )}
    </div>
  );
};

export default BulkQCBar;



