// frontend/src/components/marketing/landing/ConceptTagsSection.tsx

import React from "react";

// Установить: npm install react-fast-marquee
// Если не хочешь пакет — используем CSS-анимацию ниже как fallback
import Marquee from "react-fast-marquee";

const ROW_1 = [
  "Due Diligence", "Clause Extraction", "Risk Mapping", "M&A",
  "Data Room Analysis", "Playbook Review", "Obligation Tracking", "Deal Structuring",
];
const ROW_2 = [
  "Knowledge Graph", "Document Intelligence", "Structure Analysis",
  "Contract Review", "Audit Trail", "Source-linked Outputs", "Legal Ops", "Cross-reference",
];

function Tag({ label }: { label: string }) {
  return (
    <span className="mx-2.5 inline-flex items-center rounded-full border border-[#E5E2DA] bg-white px-4 py-1.5 text-xs font-medium text-stone-500 whitespace-nowrap">
      {label}
    </span>
  );
}

const ConceptTagsSection: React.FC = () => (
  <section className="overflow-hidden border-y border-[#E5E2DA] bg-[#F8F7F4] py-7">
    <div className="mb-3">
      <Marquee speed={28} gradient={false} pauseOnHover>
        {ROW_1.map((tag) => <Tag key={tag} label={tag} />)}
      </Marquee>
    </div>
    <Marquee speed={22} gradient={false} direction="right" pauseOnHover>
      {ROW_2.map((tag) => <Tag key={tag} label={tag} />)}
    </Marquee>
  </section>
);

export default ConceptTagsSection;


