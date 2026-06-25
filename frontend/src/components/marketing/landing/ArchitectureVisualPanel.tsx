// src/components/marketing/landing/ArchitectureVisualPanel.tsx

import React from "react";

const PIPELINE_STEPS = [
  {
    num: "01",
    title: "Input boundary",
    text: "Upload, classification and package-level grouping.",
  },
  {
    num: "02",
    title: "Evidence layer",
    text: "Source fragments, clause mapping and cross-document references.",
  },
  {
    num: "03",
    title: "Decision layer",
    text: "Risk scoring, structured findings and export-ready outputs.",
  },
] as const;

const ArchitectureVisualPanel: React.FC = () => {
  return (
    <div className="rounded-[24px] border border-[#E5E2DA] bg-white p-5">
      <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone-400">
        Pipeline view
      </p>
      <div className="mt-4 grid gap-2.5">
        {PIPELINE_STEPS.map(({ num, title, text }) => (
          <div
            key={title}
            className="rounded-[16px] border border-[#E5E2DA] bg-[#F8F7F4] px-4 py-4"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#111827] text-[11px] font-medium text-white">
                {num}
              </div>
              <div>
                <p className="text-sm font-medium text-stone-950">{title}</p>
                <p className="mt-1 text-sm leading-6 text-stone-600">{text}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ArchitectureVisualPanel;

