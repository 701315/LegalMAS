import React from "react";
import { securityContent } from "../../../content/securityContent";

const SecurityArchitectureSection: React.FC = () => {
  return (
    <section className="mt-16">
      <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 lg:p-10">
        <h2 className="text-3xl font-bold tracking-tight">
          {securityContent.architecture.title}
        </h2>

        <div className="mt-10 grid gap-6 md:grid-cols-2">
          {securityContent.architecture.blocks.map((block) => (
            <div
              key={block.title}
              className="rounded-2xl border border-white/10 bg-white/[0.02] p-6"
            >
              <h3 className="text-lg font-semibold">{block.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-slate-400">
                {block.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default SecurityArchitectureSection;


