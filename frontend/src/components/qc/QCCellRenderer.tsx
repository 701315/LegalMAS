// =============================================================
// src/components/qc/QCCellRenderer.tsx
// Отдельная колонка QC-статуса + быстрые действия.
// =============================================================

import React from "react";
import type { CheckResult, QCStatus } from "../../types";

interface QCCellRendererProps {
  value: QCStatus | undefined;
  data: CheckResult;
  onQcChange?: (
    result: CheckResult,
    newStatus: "approved" | "rejected",
  ) => void;
}

export const QCCellRenderer: React.FC<QCCellRendererProps> = ({
  value,
  data,
  onQcChange,
}) => {
  const status: QCStatus | undefined = value;

  const handleApprove = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onQcChange?.(data, "approved");
  };

  const handleReject = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onQcChange?.(data, "rejected");
  };

  const label: QCStatus = status ?? "pending";

  let color = "text-gray-600";
  if (label === "approved") color = "text-green-600";
  if (label === "rejected") color = "text-red-600";
  if (label === "needs_review") color = "text-orange-600";

  const isPending = label === "pending";

  return (
    <div className="flex items-center gap-2">
      <span className={`text-[11px] ${color}`}>{label}</span>
      {onQcChange && (
        <div className="flex gap-1">
          <button
            type="button"
            className="text-[10px] px-1 py-0.5 border rounded hover:bg-green-50 disabled:opacity-40"
            onClick={handleApprove}
            title="Подтвердить (QC approve)"
            disabled={!isPending}
          >
            ✅
          </button>
          <button
            type="button"
            className="text-[10px] px-1 py-0.5 border rounded hover:bg-red-50 disabled:opacity-40"
            onClick={handleReject}
            title="Отклонить (QC reject)"
            disabled={!isPending}
          >
            ❌
          </button>
        </div>
      )}
    </div>
  );
};

export default QCCellRenderer;
