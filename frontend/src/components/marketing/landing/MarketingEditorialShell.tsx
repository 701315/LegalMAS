import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, Shield } from "lucide-react";
import { landingContent } from "../../../content/landingContent";

interface MarketingEditorialShellProps {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
  primaryLink?: { label: string; to: string };
  secondaryLink?: { label: string; to: string };
}

const MarketingEditorialShell: React.FC<MarketingEditorialShellProps> = ({
  eyebrow,
  title,
  description,
  children,
  primaryLink,
  secondaryLink,
}) => {
  return (
    <div className="min-h-screen bg-[#f7f3ea] text-stone-950">
      <header className="sticky top-0 z-50 border-b border-stone-900/8 bg-[#f7f3ea]/90 backdrop-blur-xl supports-[backdrop-filter]:bg-[#f7f3ea]/82">
        <div className="mx-auto flex h-[72px] w-full max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:px-10 xl:px-12">
          <Link to="/" className="flex min-w-0 items-center gap-3 text-stone-900">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-stone-900/10 bg-white/80 shadow-sm">
              <Shield className="h-5 w-5" />
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

          <div className="flex items-center gap-2 sm:gap-3">
            <Link
              to="/"
              className="inline-flex items-center rounded-full border border-stone-900/10 bg-white/75 px-4 py-2.5 text-sm font-medium text-stone-800 transition-colors hover:bg-white"
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              На главную
            </Link>
          </div>
        </div>
      </header>

      <main>
        {/* Hero section */}
        <section
          id="pipeline"
          className="relative overflow-hidden border-b border-stone-900/8 bg-[#f7f3ea]"
        >
          <div className="absolute inset-x-0 top-0 h-[420px] bg-[radial-gradient(circle_at_top_left,rgba(120,113,108,0.09),transparent_40%),radial-gradient(circle_at_85%_8%,rgba(41,37,36,0.05),transparent_34%)]" />
          <div className="relative mx-auto w-full max-w-[1480px] px-4 pb-14 pt-12 sm:px-6 lg:px-10 lg:pb-20 lg:pt-16 xl:px-12">
            <div className="grid gap-8 lg:grid-cols-12 lg:items-end">
              <div className="lg:col-span-8">
                <div className="inline-flex items-center rounded-full border border-stone-900/10 bg-white/60 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone-600">
                  {eyebrow}
                </div>
                <h1 className="mt-8 max-w-5xl font-serif text-5xl leading-[0.95] tracking-[-0.04em] text-stone-950 sm:text-6xl lg:text-[5rem] xl:text-[5.5rem]">
                  {title}
                </h1>
                <p className="mt-8 max-w-3xl text-base leading-8 text-stone-700 lg:text-[1.12rem]">
                  {description}
                </p>
              </div>

              <div className="lg:col-span-4 lg:pl-6">
                <div className="rounded-[32px] border border-stone-900/10 bg-[#ece5d8] p-6 lg:p-8">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                    Explore
                  </div>
                  <div className="mt-5 space-y-3">
                    {primaryLink && (
                      <Link
                        to={primaryLink.to}
                        className="flex items-center justify-between rounded-[22px] border border-stone-900/10 bg-white/75 px-4 py-4 text-sm font-medium text-stone-900 transition-colors hover:bg-white"
                      >
                        <span>{primaryLink.label}</span>
                        <ArrowUpRight className="h-4 w-4" />
                      </Link>
                    )}
                    {secondaryLink && (
                      <Link
                        to={secondaryLink.to}
                        className="flex items-center justify-between rounded-[22px] border border-stone-900/10 bg-white/75 px-4 py-4 text-sm font-medium text-stone-900 transition-colors hover:bg-white"
                      >
                        <span>{secondaryLink.label}</span>
                        <ArrowUpRight className="h-4 w-4" />
                      </Link>
                    )}
                    <Link
                      to="/"
                      className="flex items-center justify-between rounded-[22px] border border-stone-900/10 bg-white/75 px-4 py-4 text-sm font-medium text-stone-900 transition-colors hover:bg-white"
                    >
                      <span>Вернуться к overview</span>
                      <ArrowUpRight className="h-4 w-4" />
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Content section */}
        <section className="mx-auto w-full max-w-[1480px] px-4 py-12 sm:px-6 lg:px-10 lg:py-16 xl:px-12">
          {children}
        </section>
      </main>
    </div>
  );
};

export default MarketingEditorialShell;

