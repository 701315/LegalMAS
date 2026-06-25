// frontend/src/components/marketing/solutions/SolutionsHeroSection.tsx

import React from "react";
import { solutionsContent } from "../../../content/solutionsContent";

const SolutionsHeroSection: React.FC = () => {
  const { hero } = solutionsContent;
  return (
    <section className="border-b border-[#E5E2DA] pb-14 pt-12 lg:pb-20 lg:pt-16">
      <div className="inline-flex items-center rounded-full border border-[#E5E2DA] bg-white px-4 py-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
        {hero.eyebrow}
      </div>
      <h1 className="mt-8 max-w-4xl font-serif text-5xl leading-[0.95] tracking-[-0.04em] text-stone-950 sm:text-6xl lg:text-[4.5rem]">
        {hero.title}
      </h1>
      <p className="mt-6 max-w-2xl text-base leading-8 text-stone-600">
        {hero.description}
      </p>
    </section>
  );
};

export default SolutionsHeroSection;