import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import SectionHeader from "../SectionHeader";

const SolutionsSection: React.FC = () => {
  const { capabilities } = landingContent;

  return (
    <section id="solutions" className="py-24 bg-slate-950 scroll-mt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader title={capabilities.title} />

        <div className="mt-3 max-w-2xl text-sm text-slate-400">
          {capabilities.subtitle}
        </div>

        <div className="mt-10 grid md:grid-cols-2 gap-6">
          {capabilities.featured.map((item) => (
            <div
              key={item.title}
              className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 group hover:border-white/20 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="w-11 h-11 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
                  <item.icon className="w-5 h-5 text-slate-300" />
                </div>
                <ChevronRight className="w-5 h-5 text-slate-600 group-hover:text-slate-300 transition-colors" />
              </div>

              <h3 className="mt-6 text-xl font-semibold">{item.title}</h3>
              <p className="mt-3 text-sm text-slate-400 leading-relaxed">
                {item.description}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {capabilities.support.map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-white/10 bg-white/[0.02] p-5"
            >
              <div className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/10 flex items-center justify-center">
                <item.icon className="w-4 h-4 text-slate-300" />
              </div>
              <h4 className="mt-4 text-sm font-semibold text-white">
                {item.title}
              </h4>
              <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                {item.description}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-10">
          <Link
            to="/capabilities"
            className="inline-flex items-center gap-2 text-sm text-white hover:text-slate-300 transition-colors"
          >
            Открыть подробное описание
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
};

export default SolutionsSection;

