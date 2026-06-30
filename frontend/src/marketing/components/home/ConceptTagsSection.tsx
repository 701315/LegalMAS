// src/marketing/components/home/ConceptTagsSection.tsx

import React from "react";
import Marquee from "react-fast-marquee";
import { landingContent } from "../../content/landingContent";

function Tag({ label }: { label: string }) {
  return (
    <span className="mx-3 inline-flex items-center rounded-full border border-[#E5E2DA] bg-white px-5 py-2.5 text-sm font-medium leading-none text-stone-600 whitespace-nowrap shadow-[0_1px_2px_rgba(17,24,39,0.03)]">
      {label}
    </span>
  );
}

const ConceptTagsSection: React.FC = () => {
  const { row1, row2 } = landingContent.conceptTags;

  return (
    <section className="overflow-hidden border-y border-[#E5E2DA] bg-[#F8F7F4] py-10 sm:py-12">
      <div className="mb-4">
        <Marquee speed={24} gradient={false} pauseOnHover>
          {row1.map((tag) => (
            <Tag key={tag} label={tag} />
          ))}
        </Marquee>
      </div>

      <Marquee speed={18} gradient={false} direction="right" pauseOnHover>
        {row2.map((tag) => (
          <Tag key={tag} label={tag} />
        ))}
      </Marquee>
    </section>
  );
};

export default ConceptTagsSection;

