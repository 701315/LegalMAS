// src/marketing/components/shared/MarketingPageHeader.tsx
import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

interface MarketingPageHeaderProps {
  ctaHref?: string;
  ctaLabel?: string;
  hideLeftHomeLink?: boolean;
}

const MarketingPageHeader: React.FC<MarketingPageHeaderProps> = ({
  ctaHref = "/demo",
  ctaLabel = "Запросить демо",
  hideLeftHomeLink = false,
}) => {
  return (
    <header className="border-b border-white/[0.06] bg-[#1A1917]/95 backdrop-blur-xl">
      <div
        className="mx-auto flex h-[68px] w-full items-center justify-between px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {hideLeftHomeLink ? (
          <div />
        ) : (
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-[0.9375rem] font-medium text-[#A8A29E] transition-colors hover:text-[#FAF8F5]"
          >
            <ArrowLeft className="h-4 w-4" />
            На главную
          </Link>
        )}

        <Link to={ctaHref} className="cta-primary">
          {ctaLabel}
        </Link>
      </div>
    </header>
  );
};

export default MarketingPageHeader;


