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
    <header className="border-b border-white/10 bg-slate-950/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {hideLeftHomeLink ? (
          <div />
        ) : (
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white"
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


