import React from "react";
import { Shield } from "lucide-react";

interface MarketingPageIntroProps {
  eyebrow: string;
  title: string;
  description: string;
}

const MarketingPageIntro: React.FC<MarketingPageIntroProps> = ({
  eyebrow,
  title,
  description,
}) => {
  return (
    <section className="max-w-3xl">
      <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300">
        <Shield className="w-3.5 h-3.5" />
        {eyebrow}
      </div>

      <h1 className="mt-6 text-4xl lg:text-6xl font-bold tracking-tight">{title}</h1>
      <p className="mt-6 text-lg text-slate-400 leading-relaxed">{description}</p>
    </section>
  );
};

export default MarketingPageIntro;

