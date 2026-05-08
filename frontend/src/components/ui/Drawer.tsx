// src/components/ui/Drawer.tsx

import React from "react";
import { X } from "lucide-react";
import Button from "./Button";

interface DrawerProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const Drawer: React.FC<DrawerProps> = ({
  open,
  title,
  description,
  onClose,
  children,
  footer,
}) => {
  const titleId = React.useId();
  const descriptionId = React.useId();

  const panelRef = React.useRef<HTMLDivElement | null>(null);
  const previousFocusedElementRef = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    if (!open || typeof document === "undefined") {
      return;
    }

    previousFocusedElementRef.current =
      document.activeElement as HTMLElement | null;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = window.requestAnimationFrame(() => {
      const focusable = panelRef.current?.querySelector<HTMLElement>(
        FOCUSABLE_SELECTOR,
      );
      if (focusable) {
        focusable.focus();
      } else {
        panelRef.current?.focus();
      }
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!panelRef.current) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const focusableElements = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => !element.hasAttribute("disabled"));

      if (focusableElements.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }

      const first = focusableElements[0];
      const last = focusableElements[focusableElements.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (event.shiftKey) {
        if (active === first || !panelRef.current.contains(active)) {
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
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusedElementRef.current?.focus();
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40 flex bg-black/45 backdrop-blur-[2px]">
      <div
        aria-hidden="true"
        onClick={onClose}
        className="flex-1 transition-colors duration-150"
      />

      <aside
        aria-modal="true"
        role="dialog"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className="relative h-full w-full max-w-xl shrink-0 border-l border-[var(--border-subtle)] bg-[var(--bg-card)] shadow-2xl"
      >
        <div
          ref={panelRef}
          tabIndex={-1}
          className="flex h-full flex-col outline-none"
        >
          <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
            <div className="min-w-0">
              <h2
                id={titleId}
                className="text-base font-semibold tracking-[-0.01em] text-[var(--text-primary)]"
              >
                {title}
              </h2>

              {description ? (
                <p
                  id={descriptionId}
                  className="mt-1 text-xs leading-5 text-[var(--text-muted)]"
                >
                  {description}
                </p>
              ) : null}
            </div>

            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              aria-label="Закрыть"
              className="px-2 py-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              <X size={16} />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>

          {footer ? (
            <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-5 py-3">
              {footer}
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
};

export default Drawer;




