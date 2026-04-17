import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const UseCasesSection: React.FC = () => {
  return (
    <MarketingSection id="use-cases" className="bg-slate-950 scroll-mt-24">
      <MarketingContainer size="section">
        <div className="max-w-3xl">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
            Use cases
          </div>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white lg:text-5xl">
            {landingContent.useCases.title}
          </h2>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-2">
          {landingContent.useCases.items.map((item) => {
            const Icon = item.icon;

            return (
              <div
                key={item.title}
                className="rounded-[30px] border border-white/10 bg-white/[0.03] p-8"
              >
                <Icon className="h-6 w-6 text-slate-300" />
                <h3 className="mt-8 text-2xl font-semibold text-white">{item.title}</h3>
                <p className="mt-4 text-base leading-relaxed text-slate-400">
                  {item.description}
                </p>
              </div>
            );
          })}
        </div>

        {/* CTA на подробное описание сценариев */}
        <div className="mt-10">
          <Link
            to="/solutions"
            className="inline-flex items-center gap-2 text-sm font-medium text-white transition-colors hover:text-slate-300"
          >
            Открыть подробное описание
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default UseCasesSection;


