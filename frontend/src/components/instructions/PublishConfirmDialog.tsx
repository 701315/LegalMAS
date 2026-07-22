// src/components/instructions/PublishConfirmDialog.tsx
// Диалог подтверждения публикации draft.
// Показывает имя версии и предупреждение о необратимости.

import React from "react";
import { AlertTriangle } from "lucide-react";
import Button from "../ui/Button";

interface PublishConfirmDialogProps {
  open: boolean;
  versionName: string;
  docTypeCode: string;
  isPublishing: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const PublishConfirmDialog: React.FC<PublishConfirmDialogProps> = ({
  open,
  versionName,
  docTypeCode,
  isPublishing,
  onConfirm,
  onCancel,
}) => {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="publish-dialog-title"
    >
      <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-2xl">
        {/* Header */}
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
          Подтверждение публикации
        </div>

        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[color:var(--color-warning-border,#fbbf24)] bg-[color:var(--color-warning-bg,#fef9c3)]">
            <AlertTriangle
              className="h-4 w-4 text-[color:var(--color-warning-text,#92400e)]"
              aria-hidden="true"
            />
          </div>
          <div className="min-w-0">
            <h2
              id="publish-dialog-title"
              className="text-sm font-semibold text-[var(--text-primary)]"
            >
              Опубликовать версию?
            </h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              Версия{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {versionName}
              </span>{" "}
              для типа документа{" "}
              <span className="font-mono text-[var(--text-primary)]">
                {docTypeCode}
              </span>{" "}
              будет опубликована.
            </p>
            <p className="mt-2 text-xs text-[var(--text-muted)]">
              После публикации версия станет immutable и будет использоваться
              как базовая для всех tenant. Это действие нельзя отменить —
              только создать новую версию.
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            type="button"
            onClick={onCancel}
            disabled={isPublishing}
          >
            Отмена
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="button"
            onClick={onConfirm}
            isLoading={isPublishing}
            disabled={isPublishing}
          >
            Опубликовать
          </Button>
        </div>
      </div>
    </div>
  );
};

export default PublishConfirmDialog;



