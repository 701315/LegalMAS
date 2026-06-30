// src/marketing/components/shared/SiteFooter.tsx

import React from "react";
import { Link } from "react-router-dom";
import SteloomWordmark from "./primitives/SteloomWordmark";

const LEGAL_LINKS = [
  { label: "Условия использования", href: "/legal/terms" },
  { label: "Политика конфиденциальности", href: "/legal/privacy" },
  { label: "Политика cookie", href: "/legal/cookies" },
  { label: "Политика безопасности", href: "/legal/security" },
];

const SiteFooter: React.FC = () => (
  <footer
    className="border-t border-[#E5E2DA] bg-[#F1EFEA]"
    data-header-theme="light"
  >
    <div className="mx-auto w-full max-w-[1280px] px-4 py-16 sm:px-6 lg:px-10 xl:px-12">
      {/* ── Верхняя часть: текст слева, большой логотип справа ───────────────── */}
      <div className="grid gap-10 lg:grid-cols-[1.3fr_0.7fr] lg:items-start">
        {/* Левая часть */}
        <div className="max-w-lg">
          <p className="text-sm leading-7 text-stone-500">
            Интеллектуальный слой для юридической работы.
            Проверка по playbook, выводы с привязкой к источникам
            и управляемые document workflows для M&A
            и корпоративных юридических команд.
          </p>

          <div className="mt-6 space-y-2">
            <p className="text-sm font-medium text-stone-900">
              Steloom.Com
            </p>

            <p className="text-sm text-stone-500">
              DED: 801234
            </p>

            <p className="text-sm text-stone-500">
              Office 113, Building 9, Dubai Internet CityP.O. Box 502966Dubai, UAE
            </p>

            <a
              href="mailto:hello@steloom.com"
              className="block text-sm text-stone-500 transition-colors hover:text-stone-900"
            >
              hello@steloom.com
            </a>

            <a
              href="tel:+79219125351"
              className="block text-sm text-stone-500 transition-colors hover:text-stone-900"
            >
              +7 921 912 53 51
            </a>

            <a
              href="https://www.linkedin.com/company/steloom/"
              target="_blank"
              rel="noreferrer"
              className="block text-sm text-stone-500 transition-colors hover:text-stone-900"
            >
              LinkedIn
            </a>
          </div>
        </div>

        {/* Правая часть: большой логотип */}
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

      {/* ── Нижняя часть ─────────────────────────────────────────────────────── */}
      <div className="mt-12 flex flex-col gap-4 border-t border-[#E5E2DA] pt-8 sm:flex-row sm:items-center sm:justify-between">
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

export default SiteFooter;

