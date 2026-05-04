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
      <span className="text-xs italic text-[var(--text-tertiary,#9ca3af)]">
        —
      </span>
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
            "border-[var(--color-blue,#1d4ed8)]/15 bg-[var(--color-blue-highlight,#eff6ff)] text-[var(--color-blue,#1d4ed8)]",
          )}
        >
          <span className="truncate">{trigger}</span>
        </span>
      ))}

      {hidden > 0 ? (
        <span className="text-xs text-[var(--text-tertiary,#9ca3af)]">
          +{hidden}
        </span>
      ) : null}
    </div>
  );
};

export default TriggerList;



