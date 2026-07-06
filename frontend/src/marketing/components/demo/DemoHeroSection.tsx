// frontend/src/components/marketing/demo/DemoHeroSection.tsx
import React from "react";
import { demoContent } from "../../content/demoContent";

const DemoHeroSection: React.FC = () => {
  const { hero } = demoContent;
  return (
    <section className="border-b border-[#E8E4DD] pb-14 pt-12 lg:pb-20 lg:pt-16">
      <div className="badge">
        {hero.eyebrow}
      </div>
      <h1 className="mt-8 max-w-4xl font-serif text-5xl leading-[0.95] tracking-[-0.04em] text-[#1A1917] sm:text-6xl lg:text-[4.5rem]">
        {hero.title}
      </h1>
      <p className="mt-6 max-w-2xl text-base leading-8 text-[#78756F]">
        {hero.description}
      </p>
    </section>
  );
};

export default DemoHeroSection;


