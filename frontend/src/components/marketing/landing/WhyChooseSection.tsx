import React from "react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const WhyChooseSection: React.FC = () => {
  return (
    <MarketingSection className="bg-slate-900/40">
      <MarketingContainer size="section">
        <div className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Why LegalMAS</div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white lg:text-5xl">
              {landingContent.whyChoose.title}
            </h2>
          </div>

          <div className="space-y-4">
            {landingContent.whyChoose.items.map((item) => (
              <div
                key={item.title}
                className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6 lg:p-7"
              >
                <h3 className="text-xl font-semibold text-white">{item.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-400 lg:text-base">
                  {item.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default WhyChooseSection;
