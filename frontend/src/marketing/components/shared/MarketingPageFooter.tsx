// frontend/src/marketing/components/shared/MarketingPageFooter.tsx

import React from "react";
import { Link } from "react-router-dom";
import SteloomWordmark from "./primitives/SteloomWordmark";

const LEGAL_LINKS = [
  { label: "Условия использования", href: "/legal/terms" },
  { label: "Политика конфиденциальности", href: "/legal/privacy" },
  { label: "Политика cookie", href: "/legal/cookies" },
  { label: "Политика безопасности", href: "/legal/security" },
];

const MarketingPageFooter: React.FC = () => (
  <footer
    className="border-t border-[#E5E2DA] bg-[#F1EFEA]"
    data-header-theme="light"
  >
    <div className="mx-auto w-full max-w-[1280px] px-4 py-14 sm:px-6 lg:px-10 xl:px-12">
      <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-start">
        <div className="max-w-lg">
          <p className="text-sm leading-7 text-stone-500">
            Интеллектуальный слой для юридической работы.
            Проверка по playbook, выводы с привязкой к источникам
            и управляемые document workflows для M&A
            и корпоративных юридических команд.
          </p>
        </div>

        <div className="hidden items-start justify-end lg:flex">
          <Link
            to="/"
            aria-label="Steloom — главная"
            className="text-stone-900 transition-opacity hover:opacity-40"
          >
            <SteloomWordmark height={80} />
          </Link>
        </div>
      </div>

      <div className="mt-10 flex flex-col gap-4 border-t border-[#E5E2DA] pt-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-stone-400">
          © 2026 Steloom. Все права защищены.
        </p>

        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {LEGAL_LINKS.map((l) => (
            <Link
              key={l.href}
              to={l.href}
              className="text-xs text-stone-400 transition-colors hover:text-stone-700"
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



