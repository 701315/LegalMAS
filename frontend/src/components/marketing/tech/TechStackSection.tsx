// frontend/src/components/marketing/tech/TechScaleSection.tsx

import React from "react";
import { techOverviewContent } from "../../../content/techOverviewContent";

const TechStackSection: React.FC = () => {
  const { stack } = techOverviewContent;
  return (
    <section className="mt-12">
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
        Stack
      </p>
      <h2 className="mt-4 font-serif text-3xl tracking-[-0.03em] text-stone-950 lg:text-4xl">
        {stack.title}
      </h2>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {stack.groups.map((group) => (
          <div key={group.name} className="rounded-[24px] border border-[#E5E2DA] bg-white p-6">
            <h3 className="text-base font-semibold text-stone-950">{group.name}</h3>
            <ul className="mt-5 space-y-2.5">
              {group.items.map((item) => (
                <li key={item} className="flex items-center gap-2 text-sm text-stone-600">
                  <span className="h-1 w-1 rounded-full bg-stone-300 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
};

export default TechStackSection;
