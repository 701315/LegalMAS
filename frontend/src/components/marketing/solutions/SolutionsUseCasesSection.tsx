// frontend/src/components/marketing/solutions/SolutionsUseCasesSection.tsx

import React from "react";
import { solutionsContent } from "../../../content/solutionsContent";

const SolutionsUseCasesSection: React.FC = () => {
  const { useCases } = solutionsContent;
  return (
    <section className="mt-12">
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
        Use cases
      </p>
      <h2 className="mt-4 font-serif text-3xl tracking-[-0.03em] text-stone-950 lg:text-4xl">
        {useCases.title}
      </h2>
      {useCases.subtitle && (
        <p className="mt-4 max-w-2xl text-base leading-8 text-stone-600">{useCases.subtitle}</p>
      )}
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {useCases.items.map((item) => (
          <div key={item.title} className="rounded-[24px] border border-[#E5E2DA] bg-white p-7">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[#E5E2DA] bg-[#F1EFEA]">
              <item.icon className="h-5 w-5 text-stone-600" />
            </div>
            <h3 className="mt-6 text-xl font-semibold tracking-tight text-stone-950">{item.title}</h3>
            <p className="mt-3 text-sm leading-7 text-stone-600">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default SolutionsUseCasesSection;

