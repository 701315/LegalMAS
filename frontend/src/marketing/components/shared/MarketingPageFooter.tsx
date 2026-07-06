// frontend/src/marketing/components/shared/MarketingPageFooter.tsx
import React from "react";
import { Link } from "react-router-dom";
import SteloomWordmark from "./primitives/SteloomWordmark";
import { LEGAL_LINKS } from "../../content/siteNav";

const MarketingPageFooter: React.FC = () => (
  <footer
    className="border-t border-[#E8E4DD] bg-[#F3F0EB]"
    data-header-theme="light"
  >
    <div
      className="mx-auto w-full px-6 py-14 lg:px-8"
      style={{ maxWidth: "var(--container-max-width)" }}
    >
      <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-start">
        <div className="max-w-md">
          <p className="text-[0.9375rem] leading-7 text-[#78756F]">
            Проверка по playbook, выводы с привязкой к источникам
            и управляемые document workflows для M&A
            и корпоративных юридических команд.
          </p>
        </div>
        <div className="hidden items-start justify-end lg:flex">
          <Link
            to="/"
            aria-label="Steloom — главная"
            className="text-[#1A1917] transition-opacity hover:opacity-40"
          >
            <SteloomWordmark height={72} />
          </Link>
        </div>
      </div>

      <div className="mt-10 flex flex-col gap-4 border-t border-[#E8E4DD] pt-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-[#A8A29E]">
          © 2026 Steloom. Все права защищены.
        </p>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {LEGAL_LINKS.map((l) => (
            <Link
              key={l.href}
              to={l.href}
              className="text-xs text-[#A8A29E] transition-colors hover:text-[#1A1917]"
            >
              {l.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  </footer>
);

export default MarketingPageFooter;


