import React from "react";
import { landingContent } from "../../../content/landingContent";
import SectionHeader from "../../marketing/SectionHeader";

const CapabilitiesSection: React.FC = () => {
  const { capabilities } = landingContent;

  return (
    <section id="capabilities" className="py-24 bg-slate-900 scroll-mt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader
          title={capabilities.sectionTitle}
          subtitle={capabilities.sectionSubtitle}
        />

        <div className="mt-14 grid lg:grid-cols-2 gap-6">
          {capabilities.featured.map((item) => (
            <div
              key={item.title}
              className="rounded-3xl border border-white/10 bg-gradient-to-b from-white/[0.07] to-white/[0.03] p-8 lg:p-10"
            >
              <div className="w-12 h-12 rounded-2xl bg-white text-slate-950 flex items-center justify-center">
                <item.icon className="w-6 h-6" />
              </div>
              <h3 className="mt-6 text-2xl font-semibold text-white">{item.title}</h3>
              <p className="mt-4 text-base text-slate-300 leading-relaxed">{item.description}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 grid md:grid-cols-2 gap-6">
          {capabilities.grid.map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 hover:bg-white/[0.05] transition-colors"
            >
              <div className="w-10 h-10 rounded-xl border border-white/10 bg-white/5 flex items-center justify-center">
                <item.icon className="w-5 h-5 text-slate-300" />
              </div>
              <h3 className="mt-5 text-lg font-semibold">{item.title}</h3>
              <p className="mt-3 text-sm text-slate-400 leading-relaxed">{item.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default CapabilitiesSection;

