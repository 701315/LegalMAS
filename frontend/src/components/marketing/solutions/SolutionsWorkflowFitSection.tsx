import React from "react";
import { solutionsContent } from "../../../content/solutionsContent";
import SectionHeader from "../SectionHeader";

const SolutionsWorkflowFitSection: React.FC = () => {
  const { workflows } = solutionsContent;

  return (
    <section className="mt-16">
      <SectionHeader title={workflows.title} align="left" />

      <div className="mt-10 grid md:grid-cols-3 gap-6">
        {workflows.items.map((item) => (
          <div key={item.title} className="rounded-3xl border border-white/10 bg-white/[0.03] p-8">
            <div className="w-11 h-11 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
              <item.icon className="w-5 h-5 text-slate-300" />
            </div>
            <h3 className="mt-6 text-xl font-semibold">{item.title}</h3>
            <p className="mt-4 text-sm text-slate-400 leading-relaxed">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default SolutionsWorkflowFitSection;

