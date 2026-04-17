import React from "react";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";
import MarketingButton from "../primitives/MarketingButton";

interface PremiumFinalCtaSectionProps {
  onOpenContact: () => void;
}

const PremiumFinalCtaSection: React.FC<PremiumFinalCtaSectionProps> = ({
  onOpenContact,
}) => {
  const { finalCta } = landingContent;

  return (
    <MarketingSection className="bg-slate-950">
      <MarketingContainer size="hero">
        <div className="rounded-[36px] border border-white/10 bg-white/[0.04] px-6 py-10 text-center sm:px-8 lg:px-12 lg:py-14">
          <h2 className="mx-auto max-w-4xl text-3xl font-semibold tracking-tight text-white lg:text-5xl">
            {finalCta.title}
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-slate-400 lg:text-lg">
            {finalCta.description}
          </p>

          <div className="mt-10 flex flex-col justify-center gap-3 sm:flex-row">
            <MarketingButton onClick={onOpenContact}>
              {finalCta.primary}
              <ArrowRight className="ml-2 h-4 w-4" />
            </MarketingButton>

            <MarketingButton to="/solutions" variant="secondary">
              {finalCta.secondary}
            </MarketingButton>
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default PremiumFinalCtaSection;
