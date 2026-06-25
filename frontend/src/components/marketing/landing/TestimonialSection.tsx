// src/components/marketing/landing/TestimonialSection.tsx

import React from "react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";
import { landingContent } from "../../../content/landingContent";

const TestimonialSection: React.FC = () => {
  const reveal = useScrollReveal(0);
  const { testimonial } = landingContent;

  return (
    <section className="bg-[#F1EFEA] py-24">
      <div className="mx-auto max-w-[1280px] px-6 lg:px-8">
        <div
          ref={reveal.ref as React.Ref<HTMLDivElement>}
          style={reveal.style}
          className="mx-auto max-w-[820px]"
        >
          {/* Eyebrow */}
          <div className="text-center text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">
            {testimonial.eyebrow}
          </div>

          {/* Кавычка */}
          <div
            aria-hidden="true"
            className="mx-auto mt-8 text-center font-serif text-[72px] leading-none text-[#2F5A4A] opacity-20 select-none"
          >
            "
          </div>

          {/* Цитата */}
          <blockquote className="mt-2 text-center font-serif text-2xl leading-relaxed tracking-[-0.02em] text-stone-900 lg:text-3xl">
            {testimonial.quote}
          </blockquote>

          {/* Автор */}
          <div className="mt-8 flex flex-col items-center gap-1">
            <div className="text-sm font-medium text-stone-700">
              {testimonial.author}
            </div>
            <div className="text-xs text-stone-400">
              {testimonial.company}
            </div>
          </div>

          {/* Placeholder notice — убрать когда появится реальный social proof */}
          {testimonial.placeholder && (
            <p className="mt-6 text-center text-[11px] text-stone-300">
              * Готовая структура под будущий social proof
            </p>
          )}
        </div>
      </div>
    </section>
  );
};

export default TestimonialSection;

