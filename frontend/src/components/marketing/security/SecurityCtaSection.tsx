import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { securityContent } from "../../../content/securityContent";

const SecurityCtaSection: React.FC = () => {
  return (
    <section className="mt-16 rounded-3xl border border-white/10 bg-white/[0.03] p-8 lg:p-10">
      <h2 className="text-2xl font-semibold">{securityContent.cta.title}</h2>
      <p className="mt-4 text-sm text-slate-400 leading-relaxed max-w-3xl">
        {securityContent.cta.subtitle}
      </p>

      <div className="mt-8">
        <Link
          to="/demo"
          className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-slate-200 transition-colors"
        >
          {securityContent.cta.primary}
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </section>
  );
};

export default SecurityCtaSection;

