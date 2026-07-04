// src/marketing/components/home/ConceptTagsSection.tsx
import React from "react";
import Marquee from "react-fast-marquee";
import { landingContent } from "../../content/landingContent";

function Tag({ label }: { label: string }) {
  return (
    <span className="mx-3 inline-flex cursor-default items-center whitespace-nowrap rounded-full border border-stone-200/60 bg-white/60 px-6 py-3 text-[15px] font-medium tracking-tight text-stone-600 shadow-sm backdrop-blur-sm transition-all duration-300 hover:border-stone-300 hover:bg-white hover:text-stone-900">
      {label}
    </span>
  );
}

const ConceptTagsSection: React.FC = () => {
  const { eyebrow, title, description, row1, row2 } = landingContent.conceptTags;

  return (
    <section 
      className="overflow-hidden border-b border-[#E5E2DA] bg-[#F8F7F4] py-24 sm:py-32" 
      data-header-theme="light"
    >
      <div className="mx-auto mb-16 flex w-full max-w-[1280px] flex-col items-center px-6 text-center lg:px-10 xl:px-12">
        <span className="eyebrow">{eyebrow}</span>
        
        {/* Используем white-space: pre-line для поддержки \n из контента */}
        <h2 className="section-title !mt-2 max-w-3xl whitespace-pre-line text-balance text-stone-950">
          {title}
        </h2>
        
        <p className="section-desc text-center">
          {description}
        </p>
      </div>

      <div className="relative flex flex-col gap-5">
        {/* Градиенты по краям для плавного появления/исчезновения тегов */}
        <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-24 bg-gradient-to-r from-[#F8F7F4] to-transparent sm:w-48" />
        <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-24 bg-gradient-to-l from-[#F8F7F4] to-transparent sm:w-48" />

        <div>
          <Marquee speed={32} gradient={false} pauseOnHover>
            {row1.map((tag) => (
              <Tag key={tag} label={tag} />
            ))}
            {/* Дублируем массив, чтобы избежать пустот на больших экранах */}
            {row1.map((tag) => (
              <Tag key={`dup1-${tag}`} label={tag} />
            ))}
          </Marquee>
        </div>

        <Marquee speed={24} gradient={false} direction="right" pauseOnHover>
          {row2.map((tag) => (
            <Tag key={tag} label={tag} />
          ))}
          {/* Дублируем массив, чтобы избежать пустот на больших экранах */}
          {row2.map((tag) => (
            <Tag key={`dup2-${tag}`} label={tag} />
          ))}
        </Marquee>
      </div>
    </section>
  );
};

export default ConceptTagsSection;

