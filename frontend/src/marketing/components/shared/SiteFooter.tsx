// src/marketing/components/shared/SiteFooter.tsx
import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SteloomWordmark from "./primitives/SteloomWordmark";

const SiteFooter: React.FC = () => {
  const { t } = useTranslation("marketing");

  return (
    <footer
      className="border-t border-[var(--border-color)] bg-[var(--bg-surface)]"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-14 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-start">
          <div className="max-w-md">
            <p className="text-body-sm leading-7 text-[var(--text-secondary)]">
              {t("footer.description")}
            </p>
            <div className="mt-8 space-y-3">
              <div className="pt-2">
                <a
                  href="mailto:info@steloom.com"
                  className="block text-body-sm text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                >
                  info@steloom.com
                </a>
              </div>
            </div>
          </div>
          <div className="hidden items-start justify-end lg:flex">
            <Link
              to="/"
              aria-label={t("footer.homeLabel")}
              className="text-[var(--text-primary)] transition-opacity hover:opacity-40"
            >
              <SteloomWordmark height={72} />
            </Link>
          </div>
        </div>
        <div className="mt-10 flex flex-col gap-4 border-t border-[var(--border-color)] pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[var(--text-muted)]">
            {t("footer.copyright")}
          </p>
        </div>
      </div>
    </footer>
  );
};

export default SiteFooter;

