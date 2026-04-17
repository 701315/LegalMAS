import React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";

interface FinalCtaSectionProps {
  onOpenContact: () => void;
}

const FinalCtaSection: React.FC<FinalCtaSectionProps> = ({ onOpenContact }) => {
  const navigate = useNavigate();
  const { finalCta } = landingContent;

  return (
    <section className="py-24 bg-white text-slate-950">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl lg:text-5xl font-bold tracking-tight">{finalCta.title}</h2>
        <p className="mt-5 text-base lg:text-lg text-slate-600 max-w-3xl mx-auto leading-relaxed">
          {finalCta.subtitle}
        </p>
        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <button
            onClick={onOpenContact}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-6 py-3.5 text-sm font-semibold text-white hover:bg-slate-800 transition-colors"
          >
            {finalCta.ctaPrimary}
            <ArrowRight className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate("/login")}
            className="inline-flex items-center justify-center rounded-xl border border-slate-300 px-6 py-3.5 text-sm font-semibold text-slate-950 hover:bg-slate-100 transition-colors"
          >
            {finalCta.ctaSecondary}
          </button>
        </div>
      </div>
    </section>
  );
};

export default FinalCtaSection;

