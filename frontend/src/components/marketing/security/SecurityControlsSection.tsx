import React from "react";
import { securityContent } from "../../../content/securityContent";
import SectionHeader from "../SectionHeader";

const SecurityControlsSection: React.FC = () => {
  const { controls } = securityContent;

  return (
    <section className="mt-16">
      <SectionHeader title={controls.title} subtitle={controls.subtitle} align="left" />
      <div className="mt-10 grid md:grid-cols-2 gap-6">
        {controls.items.map((item) => (
          <div
            key={item.title}
            className="rounded-3xl border border-white/10 bg-white/[0.03] p-8"
          >
            <div className="w-11 h-11 rounded-xl bg-emerald-400/10 border border-emerald-400/20 flex items-center justify-center">
              <item.icon className="w-5 h-5 text-emerald-300" />
            </div>
            <h2 className="mt-6 text-2xl font-semibold">{item.title}</h2>
            <p className="mt-4 text-sm text-slate-400 leading-relaxed">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default SecurityControlsSection;

