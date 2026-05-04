// src/components/ui/EmptyState.tsx

import React from "react";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  action,
  className,
}) => {
  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-8 text-center",
        className,
      )}
    >
      <div className="mx-auto max-w-md">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          {title}
        </h3>
        <p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">
          {description}
        </p>

        {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
      </div>
    </div>
  );
};

export default EmptyState;

