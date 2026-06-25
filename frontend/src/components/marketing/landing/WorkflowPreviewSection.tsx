// src/components/marketing/landing/WorkflowPreviewSection.tsx

import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const WorkflowPreviewSection: React.FC = () => {
  const { workflow } = landingContent;

  return (
    <MarketingSection className="bg-[#F8F7F4] scroll-mt-24">
      <MarketingContainer size="section">
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-12">

          {/* Левая колонка — заголовок */}
          <div className="lg:col-span-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Workflow
            </p>
            <h2 className="mt-4 max-w-md font-serif text-4xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-5xl">
              {workflow.title}
            </h2>
            <p className="mt-5 max-w-md text-base leading-8 text-stone-600">
              {workflow.subtitle}
            </p>

            <Link
              to="/tech#pipeline"
              className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-[#2F5A4A] transition-colors hover:text-[#3F735F]"
            >
              Открыть полный pipeline
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </div>

          {/* Правая колонка — шаги */}
          <div className="lg:col-span-8">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {workflow.steps.map((step, index) => {
                const Icon = step.icon;
                return (
                  <div
                    key={step.title}
                    className="flex h-full flex-col rounded-[24px] border border-[#E5E2DA] bg-white p-6"
                  >
                    <div className="flex items-center justify-between">
                      <Icon
                        className="h-5 w-5 text-stone-400"
                        strokeWidth={1.5}
                      />
                      <span className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">
                        0{index + 1}
                      </span>
                    </div>

                    <h3 className="mt-8 font-serif text-xl tracking-[-0.02em] text-stone-950">
                      {step.title}
                    </h3>
                    <p className="mt-3 text-sm leading-7 text-stone-600">
                      {step.text}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default WorkflowPreviewSection;

