// src/components/ui/Drawer.tsx

import React from "react";
import Button from "./Button";

interface DrawerProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

const Drawer: React.FC<DrawerProps> = ({
  open,
  title,
  description,
  onClose,
  children,
  footer,
}) => {
  React.useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex">
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Закрыть панель"
        onClick={onClose}
        className="flex-1 bg-black/20"
      />

      {/* Panel */}
      <aside
        className="relative w-full max-w-xl h-full bg-white shadow-xl border-l border-gray-200 flex flex-col"
        aria-modal="true"
        role="dialog"
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">{title}</h2>
            {description && (
              <p className="mt-1 text-xs text-gray-500">{description}</p>
            )}
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Закрыть"
            className="px-2 py-1 text-gray-500 hover:text-gray-700"
          >
            ✕
          </Button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-200 bg-gray-50">
          {footer}
        </div>
      </aside>
    </div>
  );
};

export default Drawer;

