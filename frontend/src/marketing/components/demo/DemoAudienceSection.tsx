// frontend/src/components/marketing/demo/DemoAudienceSection.tsx
import React from "react";
import { demoContent } from "../../content/demoContent";

const DemoAudienceSection: React.FC = () => {
  const { audience } = demoContent;
  return (
    <section className="mt-12">
      <div className="rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-7 lg:p-9">
        <h2 className="font-serif text-3xl tracking-[-0.03em] text-[#1A1917] lg:text-4xl">
          {audience.title}
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {audience.items.map((item) => (
            <div key={item.title} className="rounded-xl border border-[#E8E4DD] bg-white p-6">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#E8E4DD] bg-[#FAF8F5]">
                <item.icon className="h-5 w-5 text-[#78756F]" />
              </div>
              <h3 className="mt-5 text-base font-semibold text-[#1A1917]">{item.title}</h3>
              <p className="mt-2 text-sm leading-7 text-[#78756F]">{item.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default DemoAudienceSection;


