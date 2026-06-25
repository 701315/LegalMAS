// frontend/src/components/marketing/solutions/SolutionsWorkflowFitSection.tsx

import React from "react";
import { solutionsContent } from "../../../content/solutionsContent";

const SolutionsWorkflowFitSection: React.FC = () => {
  const { workflows } = solutionsContent;
  return (
    <section className="mt-12">
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
        Workflow fit
      </p>
      <h2 className="mt-4 font-serif text-3xl tracking-[-0.03em] text-stone-950 lg:text-4xl">
        {workflows.title}
      </h2>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {workflows.items.map((item) => (
          <div key={item.title} className="rounded-[24px] border border-[#E5E2DA] bg-white p-6">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[#E5E2DA] bg-[#F1EFEA]">
              <item.icon className="h-5 w-5 text-stone-600" />
            </div>
            <h3 className="mt-5 text-base font-semibold text-stone-950">{item.title}</h3>
            <p className="mt-2 text-sm leading-7 text-stone-600">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default SolutionsWorkflowFitSection;

