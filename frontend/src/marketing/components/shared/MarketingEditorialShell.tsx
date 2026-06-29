// src/components/marketing/landing/MarketingEditorialShell.tsx

import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import SteloomWordmark from "../primitives/SteloomWordmark";

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
    <div className="min-h-screen bg-[#F8F7F4] text-stone-950">

      {/* Header — идентичен LandingHeader без onOpenContact */}
      <header className="sticky top-0 z-50 border-b border-[#E5E2DA] bg-[#F8F7F4]/92 backdrop-blur-xl supports-[backdrop-filter]:bg-[#F8F7F4]/85">
        <div className="mx-auto flex h-[68px] w-full max-w-[1280px] items-center justify-between px-4 sm:px-6 lg:px-10 xl:px-12">
          <Link
            to="/"
            className="flex min-w-0 items-center text-stone-900 transition-opacity hover:opacity-60"
            aria-label="steloom — на главную"
          >
            <SteloomWordmark height={18} />
          </Link>

          <Link
            to="/"
            className="inline-flex items-center gap-2 rounded-full border border-[#E5E2DA] bg-white px-4 py-2 text-sm text-stone-600 transition-colors hover:border-stone-300 hover:text-stone-950"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            На главную
          </Link>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section
          id="pipeline"
          className="border-b border-[#E5E2DA] bg-[#F8F7F4]"
        >
          <div className="mx-auto w-full max-w-[1280px] px-4 pb-14 pt-12 sm:px-6 lg:px-10 lg:pb-20 lg:pt-16 xl:px-12">
            <div className="grid gap-8 lg:grid-cols-12 lg:items-end">

              <div className="lg:col-span-8">
                <div className="inline-flex items-center rounded-full border border-[#E5E2DA] bg-white px-4 py-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
                  {eyebrow}
                </div>
                <h1 className="mt-8 max-w-5xl font-serif text-5xl leading-[0.95] tracking-[-0.04em] text-stone-950 sm:text-6xl lg:text-[5rem] xl:text-[5.5rem]">
                  {title}
                </h1>
                <p className="mt-8 max-w-3xl text-base leading-8 text-stone-600 lg:text-[1.05rem]">
                  {description}
                </p>
              </div>

              <div className="lg:col-span-4 lg:pl-6">
                <div className="rounded-[24px] border border-[#E5E2DA] bg-[#F1EFEA] p-6 lg:p-7">
                  <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
                    Explore
                  </p>
                  <div className="mt-5 space-y-2.5">
                    {primaryLink && (
                      <Link
                        to={primaryLink.to}
                        className="flex items-center justify-between rounded-[16px] border border-[#E5E2DA] bg-white px-4 py-3.5 text-sm text-stone-700 transition-colors hover:text-stone-950"
                      >
                        <span>{primaryLink.label}</span>
                        <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
                      </Link>
                    )}
                    {secondaryLink && (
                      <Link
                        to={secondaryLink.to}
                        className="flex items-center justify-between rounded-[16px] border border-[#E5E2DA] bg-white px-4 py-3.5 text-sm text-stone-700 transition-colors hover:text-stone-950"
                      >
                        <span>{secondaryLink.label}</span>
                        <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
                      </Link>
                    )}
                    <Link
                      to="/"
                      className="flex items-center justify-between rounded-[16px] border border-[#E5E2DA] bg-white px-4 py-3.5 text-sm text-stone-700 transition-colors hover:text-stone-950"
                    >
                      <span>Вернуться к overview</span>
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
                    </Link>
                  </div>
                </div>
              </div>

            </div>
          </div>
        </section>

        {/* Content */}
        <section className="mx-auto w-full max-w-[1280px] px-4 py-12 sm:px-6 lg:px-10 lg:py-16 xl:px-12">
          {children}
        </section>
      </main>

    </div>
  );
};

export default MarketingEditorialShell;

