import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
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
    <MarketingSection id="capabilities" className="bg-[#f7f3ea] scroll-mt-24">
      <MarketingContainer size="section">
        <div className="grid gap-10 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-5">
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Capabilities
            </div>
            <h2 className="mt-4 max-w-xl font-serif text-4xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-6xl">
              {capabilities.title}
            </h2>
          </div>

          <div className="lg:col-span-7 lg:pl-8">
            <p className="max-w-2xl text-base leading-8 text-stone-700 lg:text-[1.1rem]">
              {capabilities.subtitle}
            </p>
            <Link
              to="/capabilities"
              className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-stone-900 transition-colors hover:text-stone-600"
            >
              Открыть все возможности
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </div>
        </div>

        <div className="mt-12 grid gap-5 lg:grid-cols-12">
          <div className="rounded-[32px] border border-stone-900/10 bg-[#ece5d8] p-7 lg:col-span-7 lg:p-9">
            <FeaturedPrimaryIcon className="h-6 w-6 text-stone-700" />
            <h3 className="mt-10 max-w-xl font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-[2.5rem]">
              {featuredPrimary.title}
            </h3>
            <p className="mt-5 max-w-2xl text-base leading-8 text-stone-700">
              {featuredPrimary.description}
            </p>
          </div>

          <div className="rounded-[32px] border border-stone-900/10 bg-white/70 p-7 lg:col-span-5 lg:p-9">
            <FeaturedSecondaryIcon className="h-6 w-6 text-stone-700" />
            <h3 className="mt-10 max-w-sm font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950">
              {featuredSecondary.title}
            </h3>
            <p className="mt-5 text-sm leading-7 text-stone-700 lg:text-base">
              {featuredSecondary.description}
            </p>
          </div>

          {capabilities.support.map((item) => {
            const Icon = item.icon;

            return (
              <div
                key={item.title}
                className="rounded-[28px] border border-stone-900/10 bg-white/60 p-6 lg:col-span-4"
              >
                <Icon className="h-5 w-5 text-stone-700" />
                <h3 className="mt-8 text-xl font-semibold tracking-tight text-stone-950">
                  {item.title}
                </h3>
                <p className="mt-3 text-sm leading-7 text-stone-700">{item.description}</p>
              </div>
            );
          })}
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default CapabilitiesBentoSection;


