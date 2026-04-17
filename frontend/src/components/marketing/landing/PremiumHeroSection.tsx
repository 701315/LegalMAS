import React from "react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

interface PremiumHeroSectionProps {
  onOpenContact: () => void;
}

const PremiumHeroSection: React.FC<PremiumHeroSectionProps> = () => {
  const { hero } = landingContent;

  const panelIcons = ["§", "★", "⛶", "☁"];

  return (
    <MarketingSection className="relative overflow-hidden pt-14 pb-8 lg:pt-20 lg:pb-10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(71,85,105,0.24),transparent_28%),radial-gradient(circle_at_78%_18%,rgba(37,99,235,0.18),transparent_30%),linear-gradient(180deg,#020617_0%,#020617_100%)]" />

      <MarketingContainer size="hero" className="relative">
        <div className="grid items-start gap-10 lg:grid-cols-[1.12fr_0.88fr]">
          <div className="max-w-4xl">
            <h1 className="max-w-5xl text-5xl font-semibold tracking-tight text-white sm:text-6xl lg:text-[5.5rem] lg:leading-[0.96]">
              {hero.title}
            </h1>

            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-300 lg:text-xl">
              {hero.description}
            </p>
          </div>

          <div className="lg:pl-6">
            <div className="rounded-[32px] border border-white/10 bg-white/[0.045] p-6 shadow-2xl shadow-black/30 backdrop-blur-sm lg:p-8">
              <h2 className="text-2xl font-semibold tracking-tight text-white lg:text-[1.6rem]">
                {hero.panelTitle}
              </h2>

              <div className="mt-6 space-y-4">
                {hero.panelItems.map((item, index) => (
                  <div
                    key={item}
                    className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4"
                  >
                    <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-amber-400/60 bg-slate-950/90 shadow-[0_10px_30px_rgba(0,0,0,0.55)]">
                      <span className="text-[16px] font-semibold tracking-tight text-amber-200">
                        {panelIcons[index] ?? "§"}
                      </span>
                    </div>

                    <p className="text-base font-medium leading-relaxed text-slate-100 lg:text-[17px]">
                      {item}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default PremiumHeroSection;


