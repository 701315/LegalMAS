// =============================================================
// src/pages/tabs/documents/components/ExportMenu.tsx
// =============================================================

import React, { useCallback, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight, Download } from "lucide-react";
import Button from "../ui/Button";

interface ExportMenuProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onExportExcel: () => void;
  onExportWord: () => void;
  /**
   * Optional PDF handler. When omitted, the PDF button is not rendered.
   * Used by the Requests tab where PDF is not yet supported by the backend.
   */
  onExportPDF?: () => void;
}

const ExportMenu: React.FC<ExportMenuProps> = ({
  isOpen,
  onToggle,
  onClose,
  onExportExcel,
  onExportWord,
  onExportPDF,
}) => {
  const { t } = useTranslation("common");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const slideoutId = useId();

  const restoreFocusToTrigger = useCallback(() => {
    triggerRef.current?.focus();
  }, []);

  const closeAndRestoreFocus = useCallback(() => {
    restoreFocusToTrigger();
    onClose();
  }, [restoreFocusToTrigger, onClose]);

  /**
   * Wrap an export handler so the focus returns to the trigger button
   * *before* the parent closes the menu (which collapses the slideout
   * and applies `inert`). Ordering matters: if we focused after the
   * parent state change, React would apply `inert` while focus is still
   * inside the container, and the browser would move focus to <body>.
   */
  const handleExport = useCallback(
    (handler: () => void) => () => {
      restoreFocusToTrigger();
      handler();
    },
    [restoreFocusToTrigger],
  );

  React.useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAndRestoreFocus();
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, closeAndRestoreFocus]);

  return (
    <div ref={containerRef} className="contents">
      <div className="relative flex shrink-0 items-center">
        <Button
          ref={triggerRef}
          type="button"
          size="sm"
          variant={isOpen ? "outline" : "secondary"}
          onClick={onToggle}
          aria-expanded={isOpen}
          aria-controls={slideoutId}
          leftIcon={<Download className="h-4 w-4" />}
          rightIcon={
            <ChevronRight
              className={`h-4 w-4 shrink-0 transition-transform duration-200 ${
                isOpen ? "rotate-90" : "rotate-0"
              }`}
            />
          }
          className={[
            "shrink-0 whitespace-nowrap text-xs sm:text-sm",
            isOpen
              ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
              : "",
          ].join(" ")}
        >
          <span className="sm:hidden">
            {t("exportMenu.saveShort")}
          </span>
          <span className="hidden sm:inline">
            {t("exportMenu.saveLong")}
          </span>
        </Button>

        <div
          id={slideoutId}
          className={`ml-2 hidden shrink-0 origin-left items-center gap-2 overflow-hidden transition-all duration-300 ease-out sm:flex ${
            isOpen
              ? "max-w-[340px] translate-x-0 opacity-100"
              : "pointer-events-none max-w-0 -translate-x-2 opacity-0"
          }`}
          inert={!isOpen}
        >
          <div className="flex shrink-0 items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-2 py-1.5 shadow-sm">
            <Button
              size="sm"
              variant="secondary"
              className="shrink-0 whitespace-nowrap"
              onClick={handleExport(onExportExcel)}
            >
              {t("exportMenu.excel")}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="shrink-0 whitespace-nowrap"
              onClick={handleExport(onExportWord)}
            >
              {t("exportMenu.word")}
            </Button>
            {onExportPDF ? (
              <Button
                size="sm"
                variant="secondary"
                className="shrink-0 whitespace-nowrap"
                onClick={handleExport(onExportPDF)}
              >
                {t("exportMenu.pdf")}
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      <div
        className={`basis-full overflow-hidden transition-all duration-200 ease-out sm:hidden ${
          isOpen ? "mt-2 max-h-16 opacity-100" : "max-h-0 opacity-0"
        }`}
        inert={!isOpen}
      >
        <div className="flex w-full items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-2 shadow-sm">
          <Button
            size="sm"
            variant="secondary"
            className="min-w-0 flex-1 justify-center whitespace-nowrap"
            onClick={handleExport(onExportExcel)}
          >
            {t("exportMenu.excel")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            className="min-w-0 flex-1 justify-center whitespace-nowrap"
            onClick={handleExport(onExportWord)}
          >
            {t("exportMenu.word")}
          </Button>
          {onExportPDF ? (
            <Button
              size="sm"
              variant="secondary"
              className="min-w-0 flex-1 justify-center whitespace-nowrap"
              onClick={handleExport(onExportPDF)}
            >
              {t("exportMenu.pdf")}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default ExportMenu;


