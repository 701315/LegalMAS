// src/components/ui/PageSection.tsx

import React from "react";
import { twMerge } from "tailwind-merge";

interface PageSectionProps {
  title?: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

const PageSection: React.FC<PageSectionProps> = ({
  title,
  subtitle,
  rightSlot,
  children,
  className,
}) => {
  const hasHeader = Boolean(title || subtitle || rightSlot);

  return (
    <section
      className={cn(
        "rounded-xl border border-[var(--border,#e5e7eb)] bg-[var(--bg-elevated,#ffffff)] p-4 shadow-sm",
        className,
      )}
    >
      {hasHeader ? (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            {title ? (
              <h2 className="text-sm font-semibold leading-6 text-[var(--text-primary,#111827)]">
                {title}
              </h2>
            ) : null}

            {subtitle ? (
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary,#6b7280)]">
                {subtitle}
              </p>
            ) : null}
          </div>

          {rightSlot ? <div className="shrink-0">{rightSlot}</div> : null}
        </div>
      ) : null}

      <div className="min-w-0">{children}</div>
    </section>
  );
};

export default PageSection;




