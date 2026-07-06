// frontend/src/components/marketing/demo/DemoFaqSection.tsx
import React, { useState } from "react";
import { demoContent } from "../../content/demoContent";

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[#E8E4DD]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-4 py-5 text-left"
      >
        <span className="text-[0.9375rem] font-medium leading-6 text-[#1A1917]">{question}</span>
        <span
          className="mt-0.5 shrink-0 text-[#A8A29E] transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
      </button>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 300 : 0, opacity: open ? 1 : 0 }}
      >
        <p className="pb-5 text-[0.9375rem] leading-7 text-[#78756F]">{answer}</p>
      </div>
    </div>
  );
}

const DemoFaqSection: React.FC = () => {
  const { faq } = demoContent;
  return (
    <section className="mt-12">
      <p className="eyebrow">FAQ</p>
      <h2 className="section-title !mt-4">
        {faq.title}
      </h2>
      <div className="mt-8 rounded-xl border border-[#E8E4DD] bg-white px-6 py-2">
        {faq.items.map((item) => (
          <FaqItem key={item.question} question={item.question} answer={item.answer} />
        ))}
      </div>
    </section>
  );
};

export default DemoFaqSection;


