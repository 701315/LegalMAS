import React from "react";
import { landingContent } from "../../../content/landingContent";

const PrinciplesSection: React.FC = () => {
  return (
    <section className="py-10 border-b border-white/5 bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-4">
          {landingContent.principles.title}
        </div>
        <div className="flex flex-wrap gap-3">
          {landingContent.principles.items.map((item) => (
            <div
              key={item}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300"
            >
              {item}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default PrinciplesSection;

