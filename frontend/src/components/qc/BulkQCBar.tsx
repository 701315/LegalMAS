// =============================================================
// src/components/qc/BulkQCBar.tsx
// Панель массового QC для выбранных результатов.
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

// Варианты severity для override
const SEVERITY_OPTIONS: { value: SeverityLevel; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "pass", label: "Pass" },
  { value: "unclear", label: "Unclear" },
];

// Варианты result для override (+ «не менять»)
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
    <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-[var(--border-soft)] bg-[color:color-mix(in_srgb,var(--bg-card)_92%,black)] px-4 py-2 text-xs text-[var(--text-secondary)] shadow-[0_-8px_24px_rgba(15,23,42,0.12)] backdrop-blur">
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
            className="w-64 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-muted)]"
          />

          <button
            type="button"
            className={cn(
              "rounded-lg border px-3 py-1 text-xs font-medium transition",
              "border-[color:color-mix(in_srgb,var(--success)_26%,transparent)]",
              "bg-[color:color-mix(in_srgb,var(--success)_14%,white)]",
              "text-[var(--success)]",
              "hover:bg-[color:color-mix(in_srgb,var(--success)_18%,white)]",
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
              "border-[color:color-mix(in_srgb,var(--color-error)_26%,transparent)]",
              "bg-[var(--color-error-highlight)]",
              "text-[var(--color-error)]",
              "hover:bg-[color:color-mix(in_srgb,var(--color-error)_14%,white)]",
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
                "disabled:cursor-not-allowed disabled:opacity-45",
                showOverride
                  ? "border-[color:color-mix(in_srgb,var(--color-orange)_26%,transparent)] bg-[var(--color-orange-highlight)] text-[var(--color-orange)]"
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
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-primary)] focus:ring-1 focus:ring-[var(--accent-muted)]"
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
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-primary)] focus:ring-1 focus:ring-[var(--accent-muted)]"
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
              "rounded-lg px-3 py-1 text-xs font-medium text-white transition",
              "bg-[var(--color-orange)] hover:bg-[color:color-mix(in_srgb,var(--color-orange)_84%,black)]",
              "disabled:cursor-not-allowed disabled:opacity-45",
            )}
            onClick={handleOverride}
            disabled={disabled}
          >
            Применить override
          </button>

          <button
            type="button"
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)]"
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


