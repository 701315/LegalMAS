// src/components/ui/TriggerList.tsx

import React from "react";
import { twMerge } from "tailwind-merge";

interface Props {
  triggers?: string[] | null;
  maxVisible?: number;
  className?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

export const TriggerList: React.FC<Props> = ({
  triggers,
  maxVisible = 3,
  className,
}) => {
  if (!triggers || triggers.length === 0) {
    return (
      <span className="text-xs italic text-[var(--text-tertiary)]">—</span>
    );
  }

  const normalizedMaxVisible = Number.isFinite(maxVisible)
    ? Math.max(1, Math.floor(maxVisible))
    : 3;

  const visible = triggers.slice(0, normalizedMaxVisible);
  const hidden = triggers.length - visible.length;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {visible.map((trigger) => (
        <span
          key={trigger}
          title={trigger}
          className={cn(
            "inline-flex max-w-full items-center rounded-full border px-2 py-0.5",
            "text-[11px] font-medium leading-none",
            "border-[color:color-mix(in_oklab,var(--color-blue)_15%,transparent)]",
            "bg-[var(--color-blue-highlight)]",
            "text-[var(--color-blue)]",
          )}
        >
          <span className="truncate">{trigger}</span>
        </span>
      ))}

      {hidden > 0 && (
        <span className="text-xs text-[var(--text-tertiary)]">+{hidden}</span>
      )}
    </div>
  );
};

export default TriggerList;


