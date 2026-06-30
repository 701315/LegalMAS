// frontend/src/components/marketing/demo/DemoAudienceSection.tsx

import React from "react";
import { demoContent } from "../../content/demoContent";

const DemoAudienceSection: React.FC = () => {
  const { audience } = demoContent;
  return (
    <section className="mt-12">
      <div className="rounded-[28px] border border-[#E5E2DA] bg-[#F1EFEA] p-7 lg:p-9">
        <h2 className="font-serif text-3xl tracking-[-0.03em] text-stone-950 lg:text-4xl">
          {audience.title}
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {audience.items.map((item) => (
            <div key={item.title} className="rounded-[20px] border border-[#E5E2DA] bg-white p-6">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[#E5E2DA] bg-[#F8F7F4]">
                <item.icon className="h-5 w-5 text-stone-600" />
              </div>
              <h3 className="mt-5 text-base font-semibold text-stone-950">{item.title}</h3>
              <p className="mt-2 text-sm leading-7 text-stone-600">{item.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default DemoAudienceSection;

