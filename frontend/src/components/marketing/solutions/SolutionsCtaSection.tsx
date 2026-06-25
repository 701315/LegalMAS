// frontend/src/components/marketing/solutions/SolutionsCtaSection.tsx

import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { solutionsContent } from "../../../content/solutionsContent";

const SolutionsCtaSection: React.FC = () => {
  return (
    <section className="mt-12">
      <div className="rounded-[28px] bg-[#111827] p-8 lg:p-10">
        <h2 className="font-serif text-3xl tracking-[-0.03em] text-white lg:text-4xl">
          {solutionsContent.cta.title}
        </h2>
        <p className="mt-4 max-w-2xl text-base leading-8 text-white/60">
          {solutionsContent.cta.subtitle}
        </p>
        <div className="mt-8">
          <Link
            to="/demo"
            className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-stone-950 transition-colors hover:bg-stone-100"
          >
            {solutionsContent.cta.primary}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </section>
  );
};

export default SolutionsCtaSection;


