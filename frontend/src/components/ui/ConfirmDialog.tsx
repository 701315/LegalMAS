// =============================================================
// src/components/ui/ConfirmDialog.tsx
//
// Modal dialog for action confirmation (e.g. deletion, reset).
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import Button from "./Button";

interface ConfirmDialogProps {
  /** Whether the dialog is open. */
  open: boolean;

  /** Dialog title. */
  title: string;

  /** Description or explanatory text below the title. */
  description?: string;

  /** Confirmation button text. Defaults to "Yes" via i18n. */
  confirmLabel?: string;

  /** Cancel button text. Defaults to "Cancel" via i18n. */
  cancelLabel?: string;

  /** Confirmation button variant. Defaults to "danger". */
  confirmVariant?: "danger" | "primary";

  /** Show loading indicator on the confirm button. */
  isLoading?: boolean;

  /** Callback on confirm. */
  onConfirm: () => void;

  /** Callback on cancel / close. */
  onCancel: () => void;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  confirmVariant = "danger",
  isLoading = false,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation("common");
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  const resolvedConfirmLabel =
    confirmLabel ?? t("actions.yes", { defaultValue: "Yes" });
  const resolvedCancelLabel =
    cancelLabel ?? t("actions.cancel", { defaultValue: "Cancel" });

  // Autofocus the cancel button when dialog opens
  React.useEffect(() => {
    if (open) {
      const timer = setTimeout(() => {
        cancelRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Handle Escape key press
  React.useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onCancel();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, isLoading, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby={description ? "confirm-dialog-desc" : undefined}
      onClick={() => {
        if (!isLoading) onCancel();
      }}
    >
      <div
        className="w-full max-w-sm animate-fadein rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Category label */}
        <div className="mb-3 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
          {t("dialogs.confirmation", { defaultValue: "Confirmation" })}
        </div>

        {/* Title */}
        <h2
          id="confirm-dialog-title"
          className="text-base font-semibold text-[var(--text-primary)]"
        >
          {title}
        </h2>

        {/* Description */}
        {description && (
          <p
            id="confirm-dialog-desc"
            className="mt-2 text-sm text-[var(--text-muted)]"
          >
            {description}
          </p>
        )}

        {/* Actions */}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            ref={cancelRef}
            variant="secondary"
            size="sm"
            type="button"
            onClick={onCancel}
            disabled={isLoading}
          >
            {resolvedCancelLabel}
          </Button>
          <Button
            variant={confirmVariant}
            size="sm"
            type="button"
            onClick={onConfirm}
            isLoading={isLoading}
          >
            {resolvedConfirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;


