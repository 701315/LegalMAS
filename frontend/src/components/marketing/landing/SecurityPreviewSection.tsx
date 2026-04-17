import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import SectionHeader from "../SectionHeader";

const SecurityPreviewSection: React.FC = () => {
  const { security } = landingContent;

  return (
    <section className="py-24 bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeader title={security.sectionTitle} subtitle={security.sectionSubtitle} />

        <div className="mt-8 flex flex-wrap gap-3 justify-center">
          {security.badges.map((badge) => (
            <div
              key={badge}
              className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200"
            >
              {badge}
            </div>
          ))}
        </div>

        <div className="mt-14 grid md:grid-cols-2 gap-6">
          {security.items.map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-white/10 bg-white/[0.03] p-6"
            >
              <div className="w-10 h-10 rounded-xl bg-emerald-400/10 border border-emerald-400/20 flex items-center justify-center">
                <item.icon className="w-5 h-5 text-emerald-300" />
              </div>
              <h3 className="mt-5 text-lg font-semibold">{item.title}</h3>
              <p className="mt-3 text-sm text-slate-400 leading-relaxed">{item.text}</p>
            </div>
          ))}
        </div>

        <div className="mt-10">
          <Link
            to="/security#privacy"
            className="inline-flex items-center gap-2 text-sm text-white hover:text-slate-300 transition-colors"
          >
            Подробнее о безопасности и PII-санации
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
};

export default SecurityPreviewSection;

