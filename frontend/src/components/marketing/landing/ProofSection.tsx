import React from "react";
import { Quote } from "lucide-react";
import { landingContent } from "../../../content/landingContent";

const ProofSection: React.FC = () => {
  const { proof } = landingContent;

  return (
    <section className="py-24 bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-[1.2fr_0.8fr] gap-8 items-stretch">
          <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 lg:p-10">
            <div className="w-12 h-12 rounded-2xl bg-white text-slate-950 flex items-center justify-center">
              <Quote className="w-6 h-6" />
            </div>
            <h2 className="mt-8 text-2xl lg:text-3xl font-bold">{proof.sectionTitle}</h2>
            <p className="mt-6 text-lg text-slate-300 leading-relaxed">{proof.quote}</p>
            <div className="mt-8">
              <div className="font-medium text-white">{proof.author}</div>
              <div className="text-sm text-slate-500">{proof.role}</div>
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 lg:p-10">
            <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
              Product principles
            </div>
            <div className="mt-8 space-y-6">
              {proof.metrics.map((item) => (
                <div key={item.label} className="border-b border-white/10 pb-5 last:border-0 last:pb-0">
                  <div className="text-2xl font-semibold text-white">{item.value}</div>
                  <div className="mt-1 text-sm text-slate-400">{item.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProofSection;

