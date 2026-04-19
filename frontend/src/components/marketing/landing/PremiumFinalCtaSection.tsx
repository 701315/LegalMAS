import React from "react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";
import teamImage from "../photo/сотрудники.jpg";

const PremiumFinalCtaSection: React.FC = () => {
  const { finalCta } = landingContent;

  return (
    <MarketingSection className="bg-[#f7f3ea]">
      <MarketingContainer size="section">
        <div className="rounded-[36px] border border-stone-900/10 bg-[#ece5d8] p-8 lg:p-12">
          <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-stretch lg:gap-10">
            <div className="flex flex-col justify-center">
              <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
                Final CTA
              </div>

              <h2 className="mt-4 max-w-3xl font-serif text-4xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-6xl">
                {finalCta.title}
              </h2>

              <p className="mt-5 max-w-2xl text-base leading-8 text-stone-700 lg:text-[1.05rem]">
                {finalCta.description}
              </p>
            </div>

            <div className="overflow-hidden rounded-[30px] border border-stone-900/10 bg-white/50 shadow-[0_20px_60px_rgba(28,25,23,0.08)]">
              <div className="h-full min-h-[320px] lg:min-h-[420px]">
                <img
                  src={teamImage}
                  alt="Команда LegalMAS обсуждает работу с юридическими документами"
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default PremiumFinalCtaSection;

