// src/components/marketing/landing/TrustStripSection.tsx

import React from "react";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

import officeImageOne from "../photo/офис 1.jpg";
import officeImageTwo from "../photo/офис 2.jpg";
import officeImageThree from "../photo/офис 3.jpg";

const officeImages = [officeImageOne, officeImageTwo, officeImageThree];

const TrustStripSection: React.FC = () => {
  return (
    <MarketingSection className="bg-[#F8F7F4] pt-2 lg:pt-4">
      <MarketingContainer size="section">
        <div className="rounded-[28px] border border-[#E5E2DA] bg-[#F1EFEA] p-3 lg:p-4">
          <div className="grid gap-3 md:grid-cols-3 lg:gap-4">
            {officeImages.map((src, index) => (
              <div
                key={index}
                className="overflow-hidden rounded-[20px] border border-[#E5E2DA]"
              >
                <div className="aspect-[4/5] overflow-hidden bg-[#E5E2DA]">
                  <img
                    src={src}
                    alt={`Workspace ${index + 1}`}
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

