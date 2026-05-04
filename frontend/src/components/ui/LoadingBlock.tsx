// src/components/ui/LoadingBlock.tsx

import React from "react";
import { twMerge } from "tailwind-merge";

interface LoadingBlockProps {
  text?: string;
  rows?: number;
  className?: string;
}

const ROW_WIDTHS = ["92%", "78%", "64%", "88%", "71%"] as const;

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const LoadingBlock: React.FC<LoadingBlockProps> = ({
  text = "Загрузка данных…",
  rows = 3,
  className,
}) => {
  const normalizedRows = Number.isFinite(rows) ? Math.max(1, Math.floor(rows)) : 3;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={text}
      className={cn(
        "rounded-xl border border-[var(--border,#e5e7eb)] bg-[var(--bg-elevated,#ffffff)] p-4",
        className,
      )}
    >
      <span className="sr-only">{text}</span>

      <div className="space-y-2.5">
        {Array.from({ length: normalizedRows }).map((_, index) => (
          <div
            key={index}
            aria-hidden="true"
            className={cn(
              "h-4 rounded-full animate-pulse",
              "bg-[var(--bg-elevated-soft,#f3f4f6)]",
            )}
            style={{ width: ROW_WIDTHS[index % ROW_WIDTHS.length] }}
          />
        ))}
      </div>
    </div>
  );
};

export default LoadingBlock;




