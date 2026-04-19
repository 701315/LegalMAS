import React from "react";
import { Link } from "react-router-dom";
import { Shield } from "lucide-react";
import { landingContent } from "../../../content/landingContent";

const LandingFooter: React.FC = () => {
  return (
    <footer className="border-t border-stone-900/10 bg-[#efe8db]">
      <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-10 px-4 py-10 sm:px-6 lg:px-10 xl:px-12 lg:py-14">
        <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-start">
          <div className="max-w-xl">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-stone-900/10 bg-white/80 text-stone-950 shadow-sm">
                <Shield className="h-5 w-5" />
              </div>

              <div>
                <div className="text-sm font-semibold text-stone-950">
                  {landingContent.brand.name}
                </div>
                <div className="text-xs text-stone-500">
                  {landingContent.brand.tagline}
                </div>
              </div>
            </div>

            <p className="mt-6 text-sm leading-7 text-stone-700 lg:text-base">
              Privacy-first legal document analysis for M&A, due diligence and corporate legal teams:
              playbook-driven review, source-linked outputs and controllable document workflows.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:justify-self-end lg:min-w-[460px]">
            <div className="rounded-[28px] border border-stone-900/10 bg-white/65 p-6">
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                Product
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <a
                  href="#capabilities"
                  className="text-sm text-stone-700 transition-colors hover:text-stone-950"
                >
                  Возможности
                </a>
                <a
                  href="#use-cases"
                  className="text-sm text-stone-700 transition-colors hover:text-stone-950"
                >
                  Сценарии
                </a>
                <Link
                  to="/tech#pipeline"
                  className="text-sm text-stone-700 transition-colors hover:text-stone-950"
                >
                  Архитектура
                </Link>
                <Link
                  to="/about"
                  className="text-sm text-stone-700 transition-colors hover:text-stone-950"
                >
                  О нас
                </Link>
              </div>
            </div>

            <div className="rounded-[28px] border border-stone-900/10 bg-[#f7f3ea] p-6">
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                Trust
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <Link
                  to="/security#privacy"
                  className="text-sm text-stone-700 transition-colors hover:text-stone-950"
                >
                  Безопасность
                </Link>
                <Link
                  to="/solutions"
                  className="text-sm text-stone-700 transition-colors hover:text-stone-950"
                >
                  Use cases
                </Link>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-stone-900/10 pt-6 text-xs text-stone-500 sm:flex-row sm:items-center sm:justify-between">
          <div>© 2026 LegalMAS. All rights reserved.</div>
          <div>Built for sensitive legal workflows.</div>
        </div>
      </div>
    </footer>
  );
};

export default LandingFooter;


