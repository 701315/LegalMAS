import React from "react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const PremiumHeroSection: React.FC = () => {
  const { hero } = landingContent;

  return (
    <MarketingSection className="overflow-hidden bg-[#f7f3ea] pt-8 sm:pt-10 lg:pt-14">
      <MarketingContainer size="hero">
        <div className="grid gap-8 lg:grid-cols-12 lg:items-end lg:gap-10">
          <div className="lg:col-span-7 xl:col-span-8">
            {hero.eyebrow ? (
              <div className="inline-flex items-center rounded-full border border-stone-900/10 bg-white/70 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone-600">
                {hero.eyebrow}
              </div>
            ) : null}

            <h1
              className={`max-w-5xl font-serif text-5xl leading-[0.95] tracking-[-0.045em] text-stone-950 sm:text-6xl lg:text-[5.4rem] xl:text-[6.2rem] ${
                hero.eyebrow ? "mt-8" : "mt-0"
              }`}
            >
              {hero.title}
            </h1>

            <div className="mt-8 max-w-2xl space-y-3 text-base leading-8 text-stone-700 lg:text-[1.14rem]">
              {hero.descriptionLines.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </div>

          <div className="lg:col-span-5 xl:col-span-4">
            <div className="rounded-[32px] border border-stone-900/10 bg-[#ece5d8] p-6 shadow-[0_20px_60px_rgba(28,25,23,0.08)] lg:p-7">
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                Review posture
              </div>

              <h2 className="mt-4 max-w-sm font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950">
                {hero.panelTitle}
              </h2>

              <div className="mt-6 space-y-3">
                {hero.panelItems.map((item, index) => (
                  <div
                    key={item}
                    className="rounded-[22px] border border-stone-900/10 bg-white/80 px-4 py-4"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-950 text-xs font-semibold text-[#f7f3ea]">
                        0{index + 1}
                      </div>
                      <p className="text-sm leading-6 text-stone-700">{item}</p>
                    </div>
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



