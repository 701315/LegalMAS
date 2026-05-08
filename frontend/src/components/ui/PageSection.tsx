// src/components/ui/PageSection.tsx

import React from "react";
import { twMerge } from "tailwind-merge";

interface PageSectionProps {
  title?: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  bodyClassName?: string;
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
  contentClassName,
  bodyClassName,
}) => {
  const hasHeader = Boolean(title || subtitle || rightSlot);

  return (
    <section
      className={cn(
        "min-w-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",
        "flex flex-col min-h-0",
        className,
      )}
    >
      {hasHeader ? (
        <div className="shrink-0 px-5">
          <div className="flex items-start justify-between gap-4 py-4">
            <div className="min-w-0">
              {title ? (
                <h2 className="text-base font-semibold text-[var(--text-primary)]">
                  {title}
                </h2>
              ) : null}

              {subtitle ? (
                <p className="mt-1 text-sm text-[var(--text-muted)]">
                  {subtitle}
                </p>
              ) : null}
            </div>

            {rightSlot ? <div className="shrink-0">{rightSlot}</div> : null}
          </div>

          <div className="border-t border-[var(--border-subtle)]" />
        </div>
      ) : null}

      <div
        className={cn(
          "min-w-0 px-5 py-4",
          "flex-1 min-h-0",
          contentClassName,
        )}
      >
        <div className={cn("min-w-0 min-h-0", bodyClassName ?? "flow-root")}>
          {children}
        </div>
      </div>
    </section>
  );
};

export default PageSection;




