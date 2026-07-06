// frontend/src/components/marketing/demo/DemoWhatYouSeeSection.tsx
import React from "react";
import { demoContent } from "../../content/demoContent";

const DemoWhatYouSeeSection: React.FC = () => {
  const { whatYouSee } = demoContent;
  return (
    <section className="mt-12">
      <p className="eyebrow">
        What you see
      </p>
      <h2 className="section-title !mt-4">
        {whatYouSee.title}
      </h2>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {whatYouSee.items.map((item) => (
          <div key={item.title} className="rounded-xl border border-[#E8E4DD] bg-white p-7">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#E8E4DD] bg-[#F3F0EB]">
              <item.icon className="h-5 w-5 text-[#78756F]" />
            </div>
            <h3 className="mt-6 text-xl font-semibold tracking-tight text-[#1A1917]">{item.title}</h3>
            <p className="mt-3 text-sm leading-7 text-[#78756F]">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default DemoWhatYouSeeSection;


