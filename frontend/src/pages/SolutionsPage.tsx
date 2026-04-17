import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Shield } from "lucide-react";
import SolutionsHeroSection from "../components/marketing/solutions/SolutionsHeroSection";
import SolutionsUseCasesSection from "../components/marketing/solutions/SolutionsUseCasesSection";
import SolutionsWorkflowFitSection from "../components/marketing/solutions/SolutionsWorkflowFitSection";
import SolutionsProofSection from "../components/marketing/solutions/SolutionsProofSection";

const SolutionsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl supports-[backdrop-filter]:bg-slate-950/70">
        <div className="mx-auto flex h-16 w-full max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:h-[72px] lg:px-10 xl:px-12">
          <Link to="/" className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white text-slate-950 shadow-lg shadow-black/20">
              <Shield className="h-5 w-5" />
            </div>

            <div className="min-w-0">
              <div className="truncate text-sm font-semibold tracking-tight text-white">
                LegalMAS
              </div>
              <div className="hidden truncate text-[11px] text-slate-500 sm:block">
                Enterprise legal AI infrastructure
              </div>
            </div>
          </Link>

          <Link
            to="/"
            className="inline-flex items-center rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.08]"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            На главную
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <SolutionsHeroSection />
        <SolutionsUseCasesSection />
        <SolutionsWorkflowFitSection />
        <SolutionsProofSection />
      </main>
    </div>
  );
};

export default SolutionsPage;

