import React from "react";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

import officeImageOne from "../photo/офис 1.jpg";
import officeImageTwo from "../photo/офис 2.jpg";
import officeImageThree from "../photo/офис 3.jpg";

const officeImages = [officeImageOne, officeImageTwo, officeImageThree];

const TrustStripSection: React.FC = () => {
  return (
    <MarketingSection className="bg-[#f7f3ea] pt-2 lg:pt-4">
      <MarketingContainer size="section">
        <div className="rounded-[34px] border border-stone-900/10 bg-[#f3ede3] p-3 lg:p-4">
          <div className="grid gap-3 md:grid-cols-3 lg:gap-4">
            {officeImages.map((src, index) => (
              <div key={index} className="overflow-hidden rounded-[26px] border border-stone-900/10 bg-white/60">
                <div className="aspect-[4/5] overflow-hidden bg-[#e7dfd2]">
                  <img
                    src={src}
                    alt={`Office interior and workspace view ${index + 1}`}
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default TrustStripSection;



