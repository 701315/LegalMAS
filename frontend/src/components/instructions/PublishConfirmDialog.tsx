// src/components/instructions/PublishConfirmDialog.tsx
// Диалог подтверждения публикации draft.
// Показывает имя версии и предупреждение о необратимости.

import React from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation, Trans } from "react-i18next";
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
  const { t } = useTranslation("instructions");

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
          {t("publishConfirmDialog.header")}
        </div>

        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)]">
            <AlertTriangle
              className="h-4 w-4 text-[var(--color-warning-text)]"
              aria-hidden="true"
            />
          </div>
          <div className="min-w-0">
            <h2
              id="publish-dialog-title"
              className="text-sm font-semibold text-[var(--text-primary)]"
            >
              {t("publishConfirmDialog.title")}
            </h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              <Trans
                ns="instructions"
                i18nKey="publishConfirmDialog.desc1"
                values={{ versionName, docTypeCode }}
                components={{
                  bold: <span className="font-semibold text-[var(--text-primary)]" />,
                  mono: <span className="font-mono text-[var(--text-primary)]" />,
                }}
              />
            </p>
            <p className="mt-2 text-xs text-[var(--text-muted)]">
              {t("publishConfirmDialog.desc2")}
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
            {t("publishConfirmDialog.cancel")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="button"
            onClick={onConfirm}
            isLoading={isPublishing}
            disabled={isPublishing}
          >
            {t("publishConfirmDialog.publish")}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default PublishConfirmDialog;



