// frontend/src/components/marketing/demo/DemoFaqSection.tsx

import React, { useState } from "react";
import { demoContent } from "../../../content/demoContent";

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[#E5E2DA]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-4 py-5 text-left"
      >
        <span className="text-sm font-medium leading-6 text-stone-900">{question}</span>
        <span
          className="mt-0.5 shrink-0 text-stone-400 transition-transform duration-300"
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
        <p className="pb-5 text-sm leading-7 text-stone-500">{answer}</p>
      </div>
    </div>
  );
}

const DemoFaqSection: React.FC = () => {
  const { faq } = demoContent;
  return (
    <section className="mt-12">
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">FAQ</p>
      <h2 className="mt-4 font-serif text-3xl tracking-[-0.03em] text-stone-950 lg:text-4xl">
        {faq.title}
      </h2>
      <div className="mt-8 rounded-[24px] border border-[#E5E2DA] bg-white px-6 py-2">
        {faq.items.map((item) => (
          <FaqItem key={item.question} question={item.question} answer={item.answer} />
        ))}
      </div>
    </section>
  );
};

export default DemoFaqSection;

