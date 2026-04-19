import React from "react";

const ArchitectureVisualPanel: React.FC = () => {
  return (
    <div className="rounded-[28px] border border-stone-900/10 bg-white/75 p-5">
      <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone-500">
        Pipeline view
      </div>
      <div className="mt-4 grid gap-3">
        {[
          ["01", "Input boundary", "Upload, classification and package-level grouping."],
          ["02", "Evidence layer", "Source fragments, clause mapping and cross-document references."],
          ["03", "Decision layer", "Risk scoring, structured findings and export-ready outputs."],
        ].map(([num, title, text]) => (
          <div key={title} className="rounded-[22px] bg-[#f7f3ea] px-4 py-4">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-950 text-xs font-semibold text-[#f7f3ea]">
                {num}
              </div>
              <div>
                <div className="text-sm font-semibold text-stone-950">{title}</div>
                <div className="mt-1 text-sm leading-6 text-stone-700">{text}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ArchitectureVisualPanel;

