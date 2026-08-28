// =============================================================
// src/pages/tabs/documents/components/ExportMenu.tsx
// =============================================================

import React, { useRef } from "react";
import { ChevronRight, Download } from "lucide-react";
import Button from "../../../../components/ui/Button";

interface ExportMenuProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onExportExcel: () => void;
  onExportWord: () => void;
  onExportPDF: () => void;
}

const ExportMenu: React.FC<ExportMenuProps> = ({
  isOpen,
  onToggle,
  onClose,
  onExportExcel,
  onExportWord,
  onExportPDF,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  return (
    <div ref={containerRef} className="contents">
      {/* Кнопка-триггер + desktop slideout — узкий элемент, остаётся в первой строке тулбара */}
      <div className="relative flex shrink-0 items-center">
        <Button
          type="button"
          size="sm"
          variant={isOpen ? "outline" : "secondary"}
          onClick={onToggle}
          aria-expanded={isOpen}
          aria-controls="documents-export-slideout"
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
          <span className="sm:hidden">Сохранить</span>
          <span className="hidden sm:inline">Сохранить список документов</span>
        </Button>

        {/* Desktop: slideout вправо */}
        <div
          id="documents-export-slideout"
          className={`ml-2 hidden shrink-0 origin-left items-center gap-2 overflow-hidden transition-all duration-300 ease-out sm:flex ${
            isOpen
              ? "max-w-[340px] translate-x-0 opacity-100"
              : "pointer-events-none max-w-0 -translate-x-2 opacity-0"
          }`}
          aria-hidden={!isOpen}
        >
          <div className="flex shrink-0 items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-2 py-1.5 shadow-sm">
            <Button size="sm" variant="secondary" className="shrink-0 whitespace-nowrap" onClick={onExportExcel}>
              Excel
            </Button>
            <Button size="sm" variant="secondary" className="shrink-0 whitespace-nowrap" onClick={onExportWord}>
              Word
            </Button>
            <Button size="sm" variant="secondary" className="shrink-0 whitespace-nowrap" onClick={onExportPDF}>
              PDF
            </Button>
          </div>
        </div>
      </div>

      {/* Mobile: полноширинная строка ниже, раздвигает контент вниз.
          basis-full принудительно переносит именно этот блок на новую
          строку в родительском flex-wrap, не трогая ширину кнопок выше. */}
      <div
        className={`basis-full overflow-hidden transition-all duration-200 ease-out sm:hidden ${
          isOpen ? "mt-2 max-h-16 opacity-100" : "max-h-0 opacity-0"
        }`}
        aria-hidden={!isOpen}
      >
        <div className="flex w-full items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-2 shadow-sm">
          <Button size="sm" variant="secondary" className="min-w-0 flex-1 justify-center whitespace-nowrap" onClick={onExportExcel}>
            Excel
          </Button>
          <Button size="sm" variant="secondary" className="min-w-0 flex-1 justify-center whitespace-nowrap" onClick={onExportWord}>
            Word
          </Button>
          <Button size="sm" variant="secondary" className="min-w-0 flex-1 justify-center whitespace-nowrap" onClick={onExportPDF}>
            PDF
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ExportMenu;


