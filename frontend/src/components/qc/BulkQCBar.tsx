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
  { value: "high",     label: "High" },
  { value: "medium",   label: "Medium" },
  { value: "pass",     label: "Pass" },
  { value: "unclear",  label: "Unclear" },
];

// Варианты result для override (+ «не менять»)
const RESULT_OPTIONS: { value: CheckResultValue | ""; label: string }[] = [
  { value: "",        label: "Не менять result" },
  { value: "pass",    label: "Pass" },
  { value: "fail",    label: "Fail" },
  { value: "unclear", label: "Unclear" },
];

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
    <div className="fixed bottom-0 left-0 right-0 z-30 border-t bg-white/95 backdrop-blur px-4 py-2 text-xs space-y-2">
      {/* Основная строка */}
      <div className="flex items-center justify-between">
        <div className="text-gray-700">
          Выбрано результатов:{" "}
          <span className="font-semibold">{selectedCount}</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Комментарий QC (опционально)…"
            className="text-xs border rounded px-2 py-1 w-64 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
          <button
            type="button"
            className="px-3 py-1 rounded border text-xs text-green-700 border-green-300 hover:bg-green-50 disabled:opacity-50"
            onClick={handleConfirm}
            disabled={disabled}
          >
            Подтвердить
          </button>
          <button
            type="button"
            className="px-3 py-1 rounded border text-xs text-red-700 border-red-300 hover:bg-red-50 disabled:opacity-50"
            onClick={handleReject}
            disabled={disabled}
          >
            Отклонить
          </button>
          {onOverride && (
            <button
              type="button"
              className={`px-3 py-1 rounded border text-xs disabled:opacity-50 ${
                showOverride
                  ? "bg-orange-50 text-orange-700 border-orange-300"
                  : "text-gray-700 border-gray-300 hover:bg-gray-50"
              }`}
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
        <div className="flex items-center gap-3 border-t pt-2">
          <span className="text-gray-500">Override:</span>

          {/* Severity */}
          <div className="flex items-center gap-1">
            <label className="text-gray-500">Severity:</label>
            <select
              className="border rounded px-2 py-1 text-xs"
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
            <label className="text-gray-500">Result:</label>
            <select
              className="border rounded px-2 py-1 text-xs"
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
            className="px-3 py-1 rounded bg-orange-600 text-white text-xs hover:bg-orange-700 disabled:opacity-50"
            onClick={handleOverride}
            disabled={disabled}
          >
            Применить override
          </button>
          <button
            type="button"
            className="px-3 py-1 rounded border text-xs text-gray-600 border-gray-300 hover:bg-gray-50"
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
