// src/marketing/components/shared/MarketingPageHeader.tsx
import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

interface MarketingPageHeaderProps {
  ctaHref?: string;
  ctaLabel?: string;
  hideLeftHomeLink?: boolean;
}

const MarketingPageHeader: React.FC<MarketingPageHeaderProps> = ({
  ctaHref = "/demo",
  ctaLabel,
  hideLeftHomeLink = false,
}) => {
  const { t, i18n } = useTranslation("marketing");

  // Если родитель не передал ctaLabel, используем переведенный дефолт
  const resolvedCtaLabel = ctaLabel || t("cta.demo");

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
            className="inline-flex items-center gap-2 text-body-sm font-medium text-[var(--text-muted)] transition-colors hover:text-[var(--text-inverse)]"
          >
            {/* RTL-фикс: в арабском языке иконка "назад" должна смотреть вправо */}
            <ArrowLeft
              className="h-4 w-4"
              style={{
                transform: i18n.language === "ar" ? "rotate(180deg)" : "none",
                transition: "transform 0.2s ease",
              }}
            />
            {t("header.backToHome")}
          </Link>
        )}

        <Link to={ctaHref} className="cta-primary">
          {resolvedCtaLabel}
        </Link>
      </div>
    </header>
  );
};

export default MarketingPageHeader;