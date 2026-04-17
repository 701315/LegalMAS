import React from "react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";

const TrustStripSection: React.FC = () => {
  return (
    <section className="border-y border-white/5 bg-slate-950/80">
      <MarketingContainer size="hero">
        <div className="grid gap-4 pt-3 pb-6 md:grid-cols-2 lg:pt-4 lg:pb-8 xl:grid-cols-5">
          {landingContent.trustStrip.map((item) => (
            <div
              key={item}
              className="rounded-[22px] border border-white/10 bg-white/[0.04] px-5 py-5 shadow-[0_8px_30px_rgba(2,6,23,0.22)] transition-colors hover:bg-white/[0.055]"
            >
              <div className="text-base font-medium leading-6 text-slate-100 lg:text-[17px]">
                {item}
              </div>
            </div>
          ))}
        </div>
      </MarketingContainer>
    </section>
  );
};

export default TrustStripSection;


