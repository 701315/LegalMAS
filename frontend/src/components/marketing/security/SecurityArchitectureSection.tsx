// frontend/src/components/marketing/security/SecurityArchitectureSection.tsx

import React from "react";
import { securityContent } from "../../../content/securityContent";

const SecurityArchitectureSection: React.FC = () => {
  return (
    <section className="mt-12">
      <div className="rounded-[28px] border border-[#E5E2DA] bg-[#F1EFEA] p-7 lg:p-9">
        <h2 className="font-serif text-3xl tracking-[-0.03em] text-stone-950 lg:text-4xl">
          {securityContent.architecture.title}
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {securityContent.architecture.blocks.map((block) => (
            <div
              key={block.title}
              className="rounded-[20px] border border-[#E5E2DA] bg-white p-6"
            >
              <h3 className="text-base font-semibold text-stone-950">{block.title}</h3>
              <p className="mt-3 text-sm leading-7 text-stone-600">{block.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default SecurityArchitectureSection;


