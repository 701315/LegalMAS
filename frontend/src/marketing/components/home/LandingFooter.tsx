// src/components/marketing/landing/LandingFooter.tsx

import React from "react";
import { Link } from "react-router-dom";
import SteloomWordmark from "../primitives/SteloomWordmark";

const LandingFooter: React.FC = () => {
  return (
    <footer
      className="flex items-center border-t border-[#E5E2DA] bg-[#F1EFEA]"
      style={{ minHeight: "100vh" }}
    >
      <div className="mx-auto w-full max-w-[1280px] px-6 py-16 lg:px-10 xl:px-12">

        {/* Основная сетка */}
        <div className="grid gap-12 lg:grid-cols-[1.4fr_0.6fr] lg:items-start">

          {/* Левая — описание + контакты */}
          <div className="max-w-lg">
            <p className="text-base leading-8 text-stone-600">
              Интеллектуальный слой для юридической работы. Анализ документов
              по вашему Playbook, выводы с привязкой к источнику и управляемые
              рабочие процессы для M&A и корпоративных команд.
            </p>

            {/* Контакты */}
            <div className="mt-10 space-y-4">

              <div className="flex items-start gap-4">
                <span className="w-24 shrink-0 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400 pt-0.5">
                  Company
                </span>
                <span className="text-sm text-stone-600">Steloom.com</span>
              </div>

              <div className="flex items-start gap-4">
                <span className="w-24 shrink-0 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400 pt-0.5">
                  Address
                </span>
                <span className="text-sm text-stone-600">Земля</span>
              </div>

              <div className="flex items-start gap-4">
                <span className="w-24 shrink-0 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400 pt-0.5">
                  Phone
                </span>
                <a
                  href="tel:+79219125351"
                  className="text-sm text-stone-600 transition-colors hover:text-stone-950"
                >
                  +7 921 912 53 51
                </a>
              </div>

              <div className="flex items-start gap-4">
                <span className="w-24 shrink-0 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400 pt-0.5">
                  Email
                </span>
                <a
                  href="mailto:hello@steloom.com"
                  className="text-sm text-stone-600 transition-colors hover:text-stone-950"
                >
                  hello@steloom.com
                </a>
              </div>

              <div className="flex items-start gap-4">
                <span className="w-24 shrink-0 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400 pt-0.5">
                  LinkedIn
                </span>
                <a
                  href="https://linkedin.com/company/steloom"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-stone-600 transition-colors hover:text-stone-950"
                >
                  linkedin.com/company/steloom
                </a>
              </div>

            </div>
          </div>

          {/* Правая — крупный логотип */}
          <div className="flex lg:items-start lg:justify-end">
            <Link
              to="/"
              className="inline-flex text-stone-900 transition-opacity hover:opacity-50"
              aria-label="steloom — на главную"
            >
              <SteloomWordmark height={100} />
            </Link>
          </div>

        </div>

        {/* Bottom bar */}
        <div className="mt-16 flex flex-col gap-4 border-t border-[#E5E2DA] pt-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs text-stone-400">
            © 2026 Steloom. All rights reserved.
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <a
              href="https://legora.com/legal"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-stone-400 transition-colors hover:text-stone-700"
            >
              Terms of Use
            </a>
            <a
              href="https://legora.com/legal/privacy-policy"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-stone-400 transition-colors hover:text-stone-700"
            >
              Privacy Policy
            </a>
            <a
              href="https://legora.com/legal/cookie-policy"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-stone-400 transition-colors hover:text-stone-700"
            >
              Cookie Policy
            </a>
            <a
              href="https://legora.com/legal/security"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-stone-400 transition-colors hover:text-stone-700"
            >
              Security Policy
            </a>
          </div>
        </div>

      </div>
    </footer>
  );
};

export default LandingFooter;