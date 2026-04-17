import React from "react";
import { techOverviewContent } from "../../../content/techOverviewContent";

const TechPipelineSection: React.FC = () => {
  return (
    <section className="mt-16">
      <div>
        <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
          Pipeline
        </div>
        <h2 className="mt-3 text-3xl font-bold tracking-tight lg:text-4xl">
          {techOverviewContent.pipeline.title}
        </h2>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-2">
        {techOverviewContent.pipeline.items.map((item) => (
          <div
            key={item.title}
            className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 transition-colors hover:bg-white/[0.05]"
          >
            <div className="flex items-center justify-between">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                <item.icon className="h-5 w-5 text-slate-300" />
              </div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
                {item.stage}
              </div>
            </div>

            <h3 className="mt-6 text-xl font-semibold">{item.title}</h3>
            <p className="mt-4 text-sm leading-relaxed text-slate-400">
              {item.description}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default TechPipelineSection;


