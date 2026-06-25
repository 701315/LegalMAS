// frontend/src/components/marketing/tech/TechPipelineSection.tsx

import React from "react";
import { techOverviewContent } from "../../../content/techOverviewContent";

const TechPipelineSection: React.FC = () => {
  return (
    <section className="mt-12">
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
        Pipeline
      </p>
      <h2 className="mt-4 font-serif text-3xl tracking-[-0.03em] text-stone-950 lg:text-4xl">
        {techOverviewContent.pipeline.title}
      </h2>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {techOverviewContent.pipeline.items.map((item) => (
          <div
            key={item.title}
            className="rounded-[24px] border border-[#E5E2DA] bg-white p-7"
          >
            <div className="flex items-center justify-between">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[#E5E2DA] bg-[#F1EFEA]">
                <item.icon className="h-5 w-5 text-stone-600" />
              </div>
              <span className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">
                {item.stage}
              </span>
            </div>
            <h3 className="mt-6 text-xl font-semibold tracking-tight text-stone-950">{item.title}</h3>
            <p className="mt-3 text-sm leading-7 text-stone-600">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default TechPipelineSection;

