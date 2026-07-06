// src/marketing/components/home/FaqSection.tsx
import React, { useState } from "react";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../content/landingContent";

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[#E8E4DD] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-4 py-5 text-left transition-colors hover:bg-[#FAF8F5]"
      >
        <span className="text-[0.9375rem] font-medium leading-relaxed text-[#1A1917]">
          {q}
        </span>
        <span
          className="mt-1 shrink-0 text-[#A8A29E] transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
      </button>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 240 : 0, opacity: open ? 1 : 0 }}
      >
        <p className="pb-6 pr-8 text-[0.9375rem] leading-relaxed text-[#78756F]">
          {a}
        </p>
      </div>
    </div>
  );
}

const FaqSection: React.FC = () => {
  const { faq } = landingContent;

  return (
    <section className="bg-[#F3F0EB] py-20 lg:py-28" data-header-theme="light">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-[0.4fr_0.6fr] items-start">
          {/* Левая колонка - залипает при скролле */}
          <div className="sticky top-32">
            <span className="eyebrow">{faq.eyebrow}</span>
            <h2 className="section-title text-[#1A1917]">
              {faq.title}
            </h2>
            <a href={faq.contactHref} className="cta-link mt-8">
              {faq.contactLabel}
              <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </div>

          {/* Правая колонка - скроллится */}
          <div className="flex flex-col">
            {faq.items.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default FaqSection;


