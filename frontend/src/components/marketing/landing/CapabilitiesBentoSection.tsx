import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const CapabilitiesBentoSection: React.FC = () => {
  const { capabilities } = landingContent;

  const featuredPrimary = capabilities.featured[0];
  const featuredSecondary = capabilities.featured[1];

  const FeaturedPrimaryIcon = featuredPrimary.icon;
  const FeaturedSecondaryIcon = featuredSecondary.icon;

  return (
    <MarketingSection id="capabilities" className="bg-slate-950 scroll-mt-24">
      <MarketingContainer size="section">
        <div className="max-w-3xl">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
            Capabilities
          </div>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white lg:text-5xl">
            {capabilities.title}
          </h2>
          <p className="mt-4 text-base leading-relaxed text-slate-400 lg:text-lg">
            {capabilities.subtitle}
          </p>
        </div>

        <div className="mt-12 grid gap-6 lg:grid-cols-12">
          <div className="rounded-[32px] border border-white/10 bg-white/[0.04] p-8 lg:col-span-7">
            <FeaturedPrimaryIcon className="h-6 w-6 text-slate-300" />
            <h3 className="mt-8 text-2xl font-semibold text-white lg:text-3xl">
              {featuredPrimary.title}
            </h3>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-300">
              {featuredPrimary.description}
            </p>
          </div>

          <div className="rounded-[32px] border border-white/10 bg-white/[0.03] p-8 lg:col-span-5">
            <FeaturedSecondaryIcon className="h-6 w-6 text-slate-300" />
            <h3 className="mt-8 text-2xl font-semibold text-white">
              {featuredSecondary.title}
            </h3>
            <p className="mt-4 text-sm leading-relaxed text-slate-400 lg:text-base">
              {featuredSecondary.description}
            </p>
          </div>

          {capabilities.support.map((item) => {
            const Icon = item.icon;

            return (
              <div
                key={item.title}
                className="rounded-[28px] border border-white/10 bg-white/[0.025] p-6 lg:col-span-4"
              >
                <Icon className="h-5 w-5 text-slate-300" />
                <h3 className="mt-6 text-xl font-semibold text-white">
                  {item.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-400">
                  {item.description}
                </p>
              </div>
            );
          })}
        </div>

        {/* CTA на подробное описание возможностей */}
        <div className="mt-10">
          <Link
            to="/capabilities"
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

export default CapabilitiesBentoSection;


