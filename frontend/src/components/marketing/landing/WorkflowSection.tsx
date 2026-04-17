import React from "react";
import { landingContent } from "../../../content/landingContent";
import SectionHeader from "../../marketing/SectionHeader";

const WorkflowSection: React.FC = () => {
  const { workflow } = landingContent;

  return (
    <section className="py-24 bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader title={workflow.sectionTitle} subtitle={workflow.sectionSubtitle} />
        <div className="mt-14 grid lg:grid-cols-3 gap-6">
          {workflow.steps.map((item) => (
            <div
              key={item.step}
              className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 hover:bg-white/[0.05] transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-500">{item.step}</span>
                <item.icon className="w-5 h-5 text-slate-400" />
              </div>
              <h3 className="mt-8 text-xl font-semibold">{item.title}</h3>
              <p className="mt-4 text-sm text-slate-400 leading-relaxed">{item.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default WorkflowSection;

