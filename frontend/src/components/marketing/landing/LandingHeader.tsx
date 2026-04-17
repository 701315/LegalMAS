import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Shield } from "lucide-react";
import { landingContent } from "../../../content/landingContent";

interface LandingHeaderProps {
  onOpenContact: () => void;
}

const LandingHeader: React.FC<LandingHeaderProps> = ({ onOpenContact }) => {
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl supports-[backdrop-filter]:bg-slate-950/70">
      <div className="mx-auto flex h-16 w-full max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:h-[72px] lg:px-10 xl:px-12">
        <Link to="/" className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white text-slate-950 shadow-lg shadow-black/20">
            <Shield className="h-5 w-5" />
          </div>

          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-tight text-white">
              {landingContent.brand.name}
            </div>
            <div className="hidden truncate text-[11px] text-slate-500 sm:block">
              {landingContent.brand.tagline}
            </div>
          </div>
        </Link>

        <nav className="hidden items-center gap-8 lg:flex">
          {landingContent.nav.map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="text-sm font-medium text-slate-300 transition-colors hover:text-white"
            >
              {item.label}
            </a>
          ))}

          <Link
            to="/about"
            className="text-sm font-medium text-slate-300 transition-colors hover:text-white"
          >
            О нас
          </Link>
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            onClick={() => navigate("/login")}
            className="hidden rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.08] sm:inline-flex"
          >
            Войти
          </button>

          <button
            onClick={onOpenContact}
            className="inline-flex items-center rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-slate-200 sm:px-5"
          >
            <span className="hidden sm:inline">{landingContent.hero.primaryCta}</span>
            <span className="sm:hidden">Демо</span>
            <ArrowRight className="ml-2 h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default LandingHeader;


