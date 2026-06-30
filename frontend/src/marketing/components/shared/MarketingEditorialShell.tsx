import React from "react";
import SiteHeader from "./SiteHeader";
import MarketingPageFooter from "./MarketingPageFooter";

interface MarketingEditorialShellProps {
  eyebrow?: string;
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
}) => {
  return (
    <div className="min-h-screen bg-[#F8F7F4] text-stone-950">
      <SiteHeader forcedTheme="light" hideLogin />

      <main style={{ paddingTop: 68 }}>
        <section className="border-b border-[#E5E2DA] bg-[#F8F7F4]">
          <div className="mx-auto w-full max-w-[1280px] px-4 pb-14 pt-12 sm:px-6 lg:px-10 lg:pb-20 lg:pt-16 xl:px-12">
            <div className="max-w-5xl">
              {eyebrow ? (
                <div className="inline-flex items-center rounded-full border border-[#E5E2DA] bg-white px-4 py-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
                  {eyebrow}
                </div>
              ) : null}

              <h1
                className={`max-w-5xl font-serif text-5xl leading-[0.95] tracking-[-0.04em] text-stone-950 sm:text-6xl lg:text-[5rem] xl:text-[5.5rem] ${
                  eyebrow ? "mt-8" : "mt-0"
                }`}
              >
                {title}
              </h1>

              <p className="mt-8 max-w-3xl text-base leading-8 text-stone-600 lg:text-[1.05rem]">
                {description}
              </p>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-[1280px] px-4 py-12 sm:px-6 lg:px-10 lg:py-16 xl:px-12">
          {children}
        </section>
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default MarketingEditorialShell;

