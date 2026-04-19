import React from "react";

const EditorialHeroVisual: React.FC = () => {
  return (
    <div className="relative overflow-hidden rounded-[32px] border border-stone-900/10 bg-[#e9e1d2] p-6 shadow-[0_24px_80px_rgba(28,25,23,0.08)] lg:p-8">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(255,255,255,0.55),transparent_28%),radial-gradient(circle_at_82%_14%,rgba(120,113,108,0.16),transparent_26%),linear-gradient(180deg,rgba(255,255,255,0.2),rgba(255,255,255,0))]" />

      <div className="relative">
        <div className="rounded-[24px] border border-stone-900/10 bg-white/80 p-4">
          <div className="flex items-center justify-between border-b border-stone-900/10 pb-3">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                Matter workspace
              </div>
              <div className="mt-1 text-sm font-semibold text-stone-900">
                DD package review
              </div>
            </div>
            <div className="rounded-full bg-emerald-950 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-emerald-50">
              Active
            </div>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="rounded-[18px] border border-stone-900/10 bg-[#f7f3ea] p-4">
              <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone-500">
                Package map
              </div>
              <div className="mt-4 space-y-3">
                {[
                  ["SPA_v12.pdf", "critical clause drift"],
                  ["Disclosure_Letter.docx", "2 unresolved references"],
                  ["Corporate_Approvals.pdf", "board consent detected"],
                ].map(([file, note]) => (
                  <div key={file} className="rounded-2xl border border-stone-900/10 bg-white/90 px-3 py-3">
                    <div className="text-sm font-medium text-stone-900">{file}</div>
                    <div className="mt-1 text-xs text-stone-500">{note}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-[18px] border border-stone-900/10 bg-stone-950 p-4 text-[#f7f3ea]">
                <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone-400">
                  Playbook check
                </div>
                <div className="mt-3 text-sm font-medium leading-6 text-white">
                  Change-of-control clause deviates from approved standard.
                </div>
                <div className="mt-3 text-xs leading-5 text-stone-300">
                  Linked to source paragraph, version history and negotiation note.
                </div>
              </div>

              <div className="rounded-[18px] border border-stone-900/10 bg-white/85 p-4">
                <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone-500">
                  Review summary
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {[
                    ["18", "checks passed"],
                    ["4", "risks flagged"],
                    ["9", "source links"],
                  ].map(([value, label]) => (
                    <div key={label} className="rounded-2xl bg-[#f3ecdf] px-3 py-3 text-center">
                      <div className="text-lg font-semibold text-stone-950">{value}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-stone-500">
                        {label}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EditorialHeroVisual;

