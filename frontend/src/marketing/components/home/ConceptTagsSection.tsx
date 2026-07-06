// src/marketing/components/home/ConceptTagsSection.tsx
import React from "react";
import Marquee from "react-fast-marquee";
import { landingContent } from "../../content/landingContent";

function Tag({ label }: { label: string }) {
  return (
    <span className="mx-3 inline-flex cursor-default items-center whitespace-nowrap rounded-full border border-[#E8E4DD] bg-white px-6 py-3 text-[0.9375rem] font-medium tracking-tight text-[#78756F] transition-all duration-300 hover:border-[#D6D0C7] hover:text-[#1A1917]">
      {label}
    </span>
  );
}

const ConceptTagsSection: React.FC = () => {
  const { eyebrow, title, description, row1, row2 } = landingContent.conceptTags;

  return (
    <section 
      className="overflow-hidden border-b border-[#E8E4DD] bg-[#FAF8F5] py-20 lg:py-28" 
      data-header-theme="light"
    >
      <div
        className="mx-auto mb-16 flex w-full flex-col items-center px-6 text-center lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <span className="eyebrow">{eyebrow}</span>
        
        {/* Используем white-space: pre-line для поддержки \n из контента */}
        <h2 className="section-title !mt-2 max-w-3xl whitespace-pre-line text-balance text-[#1A1917]">
          {title}
        </h2>
        
        <p className="section-desc text-center">
          {description}
        </p>
      </div>

      <div className="relative flex flex-col gap-5">
        {/* Градиенты по краям для плавного появления/исчезновения тегов */}
        <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-24 bg-gradient-to-r from-[#FAF8F5] to-transparent sm:w-48" />
        <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-24 bg-gradient-to-l from-[#FAF8F5] to-transparent sm:w-48" />

        <div>
          <Marquee speed={32} gradient={false} pauseOnHover>
            {row1.map((tag) => (
              <Tag key={tag} label={tag} />
            ))}
            {row1.map((tag) => (
              <Tag key={`dup1-${tag}`} label={tag} />
            ))}
          </Marquee>
        </div>

        <Marquee speed={24} gradient={false} direction="right" pauseOnHover>
          {row2.map((tag) => (
            <Tag key={tag} label={tag} />
          ))}
          {row2.map((tag) => (
            <Tag key={`dup2-${tag}`} label={tag} />
          ))}
        </Marquee>
      </div>
    </section>
  );
};

export default ConceptTagsSection;


