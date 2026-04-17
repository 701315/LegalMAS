import React from "react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const WorkflowPreviewSection: React.FC = () => {
  const { workflow } = landingContent;

  return (
    <MarketingSection className="bg-slate-950">
      <MarketingContainer size="section">
        <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Document flow</div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white lg:text-5xl">
              {workflow.title}
            </h2>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-400 lg:text-lg">
              {workflow.subtitle}
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {workflow.steps.map((step, idx) => (
              <div
                key={step.title}
                className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6"
              >
                <div className="flex items-center justify-between">
                  <step.icon className="h-5 w-5 text-slate-300" />
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                    0{idx + 1}
                  </div>
                </div>
                <h3 className="mt-6 text-xl font-semibold text-white">{step.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-400">{step.text}</p>
              </div>
            ))}
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default WorkflowPreviewSection;
