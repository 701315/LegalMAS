// src/components/ui/PageSection.tsx

import React from "react";

interface PageSectionProps {
  title?: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const PageSection: React.FC<PageSectionProps> = ({
  title,
  subtitle,
  rightSlot,
  children,
  className,
}) => {
  return (
    <section className={cn("rounded-lg border bg-white p-4", className)}>
      {(title || subtitle || rightSlot) && (
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            {title && (
              <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
            )}
            {subtitle && (
              <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
            )}
          </div>

          {rightSlot && <div className="shrink-0">{rightSlot}</div>}
        </div>
      )}

      {children}
    </section>
  );
};

export default PageSection;


