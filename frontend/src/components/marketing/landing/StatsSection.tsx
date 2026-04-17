import React from "react";
import { landingContent } from "../../../content/landingContent";

const StatsSection: React.FC = () => {
  return (
    <section className="border-y border-white/5 bg-slate-900/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 lg:py-10">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
          {landingContent.stats.map((item) => (
            <div key={item.label}>
              <div className="text-2xl lg:text-3xl font-semibold text-white">{item.value}</div>
              <div className="mt-1 text-sm text-slate-500 leading-relaxed">{item.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default StatsSection;

