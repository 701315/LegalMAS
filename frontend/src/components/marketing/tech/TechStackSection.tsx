import React from "react";
import { techOverviewContent } from "../../../content/techOverviewContent";
import SectionHeader from "../SectionHeader";

const TechStackSection: React.FC = () => {
  const { stack } = techOverviewContent;

  return (
    <section className="mt-16">
      <SectionHeader title={stack.title} align="left" />

      <div className="mt-10 grid md:grid-cols-3 gap-6">
        {stack.groups.map((group) => (
          <div
            key={group.name}
            className="rounded-3xl border border-white/10 bg-white/[0.03] p-8"
          >
            <h3 className="text-xl font-semibold">{group.name}</h3>
            <ul className="mt-6 space-y-3 text-sm text-slate-400">
              {group.items.map((item) => (
                <li key={item}>- {item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
};

export default TechStackSection;
