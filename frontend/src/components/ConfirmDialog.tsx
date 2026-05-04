// src/components/ConfirmDialog.tsx

import React, { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import Button from "./ui/Button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isConfirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  isConfirming = false,
  onConfirm,
  onCancel,
}) => {
  const titleId = useId();
  const descriptionId = useId();

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusedElementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previousFocusedElementRef.current =
      (document.activeElement as HTMLElement | null) ?? null;
    document.body.style.overflow = "hidden";

    const frame = window.requestAnimationFrame(() => {
      cancelButtonRef.current?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!dialogRef.current) return;

      if (event.key === "Escape") {
        event.preventDefault();
        if (!isConfirming) {
          onCancel();
        }
        return;
      }

      if (event.key !== "Tab") return;

      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        FOCUSABLE_SELECTOR,
      );

      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (event.shiftKey) {
        if (active === first || !dialogRef.current.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
      previousFocusedElementRef.current?.focus();
    };
  }, [open, onCancel, isConfirming]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <button
        type="button"
        aria-label="Закрыть диалог"
        className="absolute inset-0"
        onClick={() => {
          if (!isConfirming) {
            onCancel();
          }
        }}
      />

      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="relative z-10 w-full max-w-sm rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-xl"
      >
        <div className="space-y-2">
          <h2
            id={titleId}
            className="text-base font-semibold tracking-tight text-[var(--text-primary)]"
          >
            {title}
          </h2>

          <p
            id={descriptionId}
            className="text-sm leading-6 text-[var(--text-secondary)]"
          >
            {description}
          </p>
        </div>

        <div className="mt-5 flex items-center justify-end gap-3 border-t border-[var(--border-soft)] pt-4">
          <Button
            ref={cancelButtonRef}
            type="button"
            variant="secondary"
            size="sm"
            onClick={onCancel}
            disabled={isConfirming}
          >
            {cancelLabel}
          </Button>

          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={onConfirm}
            disabled={isConfirming}
          >
            {isConfirming ? "Удаляем..." : confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
};

export default ConfirmDialog;



