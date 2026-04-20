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
    <header className="sticky top-0 z-50 border-b border-stone-900/8 bg-[#f7f3ea]/90 backdrop-blur-xl supports-[backdrop-filter]:bg-[#f7f3ea]/82">
      <div className="mx-auto flex h-[72px] w-full max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:px-10 xl:px-12">
        <Link to="/" className="flex min-w-0 items-center gap-3 text-stone-900">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-stone-900/10 bg-white/80 shadow-sm">
            <Shield className="h-5 w-5 text-stone-900" />
          </div>

          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-[0.01em] text-stone-900">
              {landingContent.brand.name}
            </div>
            <div className="hidden truncate text-[11px] text-stone-500 sm:block">
              {landingContent.brand.tagline}
            </div>
          </div>
        </Link>

        <nav className="hidden items-center gap-8 lg:flex">
          {landingContent.nav.map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="text-sm font-medium text-stone-600 transition-colors hover:text-stone-950"
            >
              {item.label}
            </a>
          ))}

          <Link
            to="/about"
            className="text-sm font-medium text-stone-600 transition-colors hover:text-stone-950"
          >
            О нас
          </Link>
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={() => navigate("/login")}
            className="hidden rounded-full border border-stone-900/10 bg-white/70 px-4 py-2.5 text-sm font-medium text-stone-800 transition-colors hover:bg-white sm:inline-flex"
          >
            Войти
          </button>

          <button
            type="button"
            onClick={onOpenContact}
            className="inline-flex items-center rounded-full bg-stone-950 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-stone-800 sm:px-5"
          >
            <span className="hidden text-white sm:inline">Запросить демо</span>
            <span className="text-white sm:hidden">Демо</span>
            <ArrowRight className="ml-2 h-4 w-4 text-white" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default LandingHeader;



