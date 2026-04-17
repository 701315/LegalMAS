import React from "react";
import { Link } from "react-router-dom";
import { Shield } from "lucide-react";
import { landingContent } from "../../../content/landingContent";

interface LandingFooterProps {
  onOpenContact: () => void;
}

const LandingFooter: React.FC<LandingFooterProps> = ({ onOpenContact }) => {
  return (
    <footer className="border-t border-white/10 bg-slate-950">
      <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-10 px-4 py-10 sm:px-6 lg:px-10 xl:px-12">
        <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-start">
          <div className="max-w-xl">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white text-slate-950">
                <Shield className="h-5 w-5" />
              </div>

              <div>
                <div className="text-sm font-semibold text-white">
                  {landingContent.brand.name}
                </div>
                <div className="text-xs text-slate-500">
                  {landingContent.brand.tagline}
                </div>
              </div>
            </div>

            <p className="mt-5 text-sm leading-relaxed text-slate-400">
              Privacy-first legal document analysis for M&A, due diligence and corporate legal teams:
              playbook-driven review, source-linked outputs and controllable document workflows.
            </p>
          </div>

          <div className="grid gap-8 sm:grid-cols-2 lg:justify-self-end">
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Product
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <a
                  href="#capabilities"
                  className="text-sm text-slate-300 transition-colors hover:text-white"
                >
                  Возможности
                </a>

                <a
                  href="#use-cases"
                  className="text-sm text-slate-300 transition-colors hover:text-white"
                >
                  Сценарии
                </a>

                <Link
                  to="/tech#pipeline"
                  className="text-sm text-slate-300 transition-colors hover:text-white"
                >
                  Архитектура
                </Link>

                <Link
                  to="/about"
                  className="text-sm text-slate-300 transition-colors hover:text-white"
                >
                  О нас
                </Link>
              </div>
            </div>

            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Trust
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <Link
                  to="/security#privacy"
                  className="text-sm text-slate-300 transition-colors hover:text-white"
                >
                  Безопасность
                </Link>

                <Link
                  to="/solutions"
                  className="text-sm text-slate-300 transition-colors hover:text-white"
                >
                  Use cases
                </Link>

                <button
                  onClick={onOpenContact}
                  className="text-left text-sm text-slate-300 transition-colors hover:text-white"
                >
                  Запросить демо
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-white/10 pt-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <div>© 2026 LegalMAS. All rights reserved.</div>
          <div>Built for sensitive legal workflows.</div>
        </div>
      </div>
    </footer>
  );
};

export default LandingFooter;


