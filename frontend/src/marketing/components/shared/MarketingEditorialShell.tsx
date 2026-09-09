// src/marketing/components/shared/MarketingEditorialShell.tsx
import React from "react";
import SiteHeader from "./SiteHeader";
import MarketingPageFooter from "./MarketingPageFooter";

interface MarketingEditorialShellProps {
  eyebrow?: string;
  title: string;
  description: string;
  children: React.ReactNode;
}

const MarketingEditorialShell: React.FC<MarketingEditorialShellProps> = ({
  eyebrow,
  title,
  description,
  children,
}) => {
  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader variant="default" />
      <main style={{ paddingTop: 68 }}>
        {/* Hero section */}
        <section className="border-b border-[var(--border-color)]">
          <div
            className="mx-auto w-full px-6 pb-16 pt-14 lg:px-8 lg:pb-24 lg:pt-20"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            <div className="max-w-4xl">
              {eyebrow && (
                <div className="eyebrow">{eyebrow}</div>
              )}
              
              {/* Добавлен whitespace-pre-line для поддержки \n из пропсов */}
              <h1
                className="font-serif text-display leading-[1.05] tracking-[-0.03em] text-[var(--text-primary)] whitespace-pre-line"
                style={{ marginTop: eyebrow ? "1rem" : "0" }}
              >
                {title}
              </h1>
              
              <p className="mt-6 max-w-3xl text-body leading-[1.7] text-[var(--text-secondary)]">
                {description}
              </p>
            </div>
          </div>
        </section>

        {/* Content */}
        <section
          className="mx-auto w-full px-6 py-16 lg:px-8 lg:py-20"
          style={{ maxWidth: "var(--container-max-width)" }}
        >
          {children}
        </section>
      </main>
      <MarketingPageFooter />
    </div>
  );
};

export default MarketingEditorialShell;