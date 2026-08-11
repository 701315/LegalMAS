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
    <div ref={containerRef} className="relative flex items-center">
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
            className={`h-4 w-4 transition-transform duration-200 ${
              isOpen ? "rotate-90" : "rotate-0"
            }`}
          />
        }
        className={
          isOpen
            ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
            : ""
        }
      >
        Сохранить список документов
      </Button>

      <div
        id="documents-export-slideout"
        className={`ml-2 flex origin-left items-center gap-2 overflow-hidden transition-all duration-300 ease-out ${
          isOpen
            ? "max-w-[340px] translate-x-0 opacity-100"
            : "pointer-events-none max-w-0 -translate-x-2 opacity-0"
        }`}
        aria-hidden={!isOpen}
      >
        <div className="flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-2 py-1.5 shadow-sm">
          <Button size="sm" variant="secondary" onClick={onExportExcel}>
            Excel
          </Button>
          <Button size="sm" variant="secondary" onClick={onExportWord}>
            Word
          </Button>
          <Button size="sm" variant="secondary" onClick={onExportPDF}>
            PDF
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ExportMenu;


