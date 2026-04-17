import React from "react";
import { landingContent } from "../../../content/landingContent";
import { Shield } from "lucide-react";

const HeroSection: React.FC = () => {
  const { hero } = landingContent;

  return (
    <section className="relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(148,163,184,0.26),transparent_55%)]" />
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-4 pb-16 pt-20 sm:px-6 lg:px-8 lg:pb-24 lg:pt-28">
        <div className="max-w-4xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300">
            <Shield className="h-3.5 w-3.5 text-emerald-300" />
            {hero.eyebrow}
          </div>

          <h1 className="mt-8 text-5xl font-bold leading-[1.02] tracking-tight lg:text-7xl">
            {hero.title} <span className="text-slate-300">{hero.accent}</span>
          </h1>

          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-300 lg:text-xl">
            {hero.description}
          </p>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;


