import React from "react";
import { solutionsContent } from "../../../content/solutionsContent";
import SectionHeader from "../SectionHeader";

const SolutionsUseCasesSection: React.FC = () => {
  const { useCases } = solutionsContent;

  return (
    <section className="mt-16">
      <SectionHeader title={useCases.title} subtitle={useCases.subtitle} align="left" />

      <div className="mt-10 grid md:grid-cols-2 gap-6">
        {useCases.items.map((item) => (
          <div key={item.title} className="rounded-3xl border border-white/10 bg-white/[0.03] p-8">
            <div className="w-11 h-11 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
              <item.icon className="w-5 h-5 text-slate-300" />
            </div>
            <h2 className="mt-6 text-2xl font-semibold">{item.title}</h2>
            <p className="mt-4 text-sm text-slate-400 leading-relaxed">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default SolutionsUseCasesSection;

