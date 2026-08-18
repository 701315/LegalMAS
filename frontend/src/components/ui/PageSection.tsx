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
          <div className="flex flex-col gap-3 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
            <div className="min-w-0">
              {title ? (
                // было: text-base, стало: text-sm
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                  {title}
                </h2>
              ) : null}


              {subtitle ? (
                // было: text-sm mt-1, стало: text-[11px] mt-0.5
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                  {subtitle}
                </p>
              ) : null}
            </div>


            {rightSlot ? (
              <div className="w-full shrink-0 sm:w-auto">{rightSlot}</div>
            ) : null}
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



