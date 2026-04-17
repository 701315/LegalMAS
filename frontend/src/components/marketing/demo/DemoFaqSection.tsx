import React from "react";
import { demoContent } from "../../../content/demoContent";
import SectionHeader from "../SectionHeader";

const DemoFaqSection: React.FC = () => {
  const { faq } = demoContent;

  return (
    <section className="mt-16">
      <SectionHeader title={faq.title} align="left" />

      <div className="mt-10 space-y-4">
        {faq.items.map((item) => (
          <div key={item.question} className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
            <h3 className="text-lg font-semibold">{item.question}</h3>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">{item.answer}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default DemoFaqSection;

