// =============================================================
// src/components/ui/ConfirmDialog.tsx
// Переиспользуемый модальный диалог подтверждения действия.
//
// Поддерживает:
// - заголовок и описание;
// - настраиваемый текст кнопок;
// - выбор варианта кнопки подтверждения (danger / primary);
// - закрытие по клику на оверлей;
// - закрытие по Escape;
// - автофокус на кнопке отмены для безопасности.
// =============================================================

import React from "react";
import Button from "./Button";

interface ConfirmDialogProps {
  /** Показывать ли диалог. */
  open: boolean;

  /** Заголовок диалога. */
  title: string;

  /** Описание / пояснение под заголовком. */
  description?: string;

  /** Текст кнопки подтверждения. По умолчанию "Да". */
  confirmLabel?: string;

  /** Текст кнопки отмены. По умолчанию "Отмена". */
  cancelLabel?: string;

  /** Вариант кнопки подтверждения. По умолчанию "danger". */
  confirmVariant?: "danger" | "primary";

  /** Показывать индикатор загрузки на кнопке подтверждения. */
  isLoading?: boolean;

  /** Колбэк при подтверждении. */
  onConfirm: () => void;

  /** Колбэк при отмене / закрытии. */
  onCancel: () => void;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  confirmLabel = "Да",
  cancelLabel = "Отмена",
  confirmVariant = "danger",
  isLoading = false,
  onConfirm,
  onCancel,
}) => {
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  // Автофокус на кнопке отмены при открытии
  React.useEffect(() => {
    if (open) {
      // Небольшая задержка, чтобы DOM успел отрисоваться
      const timer = setTimeout(() => {
        cancelRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Закрытие по Escape
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
        {/* Метка */}
        <div className="mb-3 text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
          ПОДТВЕРЖДЕНИЕ
        </div>

        {/* Заголовок */}
        <h2
          id="confirm-dialog-title"
          className="text-base font-semibold text-[var(--text-primary)]"
        >
          {title}
        </h2>

        {/* Описание */}
        {description && (
          <p
            id="confirm-dialog-desc"
            className="mt-2 text-sm text-[var(--text-muted)]"
          >
            {description}
          </p>
        )}

        {/* Кнопки */}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            ref={cancelRef}
            variant="secondary"
            size="sm"
            type="button"
            onClick={onCancel}
            disabled={isLoading}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={confirmVariant}
            size="sm"
            type="button"
            onClick={onConfirm}
            isLoading={isLoading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;


