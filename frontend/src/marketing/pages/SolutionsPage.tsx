import React from "react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { landingContent } from "../content/landingContent";
import {
  Handshake,
  FileText,
  Scale,
  ClipboardCheck,
  SearchCheck,
} from "lucide-react";

const TAB_ICONS = [Handshake, FileText, Scale, ClipboardCheck];

const SolutionsPage: React.FC = () => {
  const { useCases } = landingContent;

  const items = [
    ...useCases.tabs.map((tab, i) => ({
      icon: TAB_ICONS[i] ?? FileText,
      title: tab.label,
      description: tab.body,
    })),
    {
      icon: SearchCheck,
      title: "Проверка активов / партнёров",
      description:
        "Проведение дополнительной проверки активов / контрагентов из анализируемых документов по выбранным критериям через сторонние сервисы и агрегирование результатов их проверки в основной отчёт.",
    },
  ];

  const leftToneByIndex: string[] = [
    "bg-white/70",
    "bg-[#efe9dd]",
    "bg-white/75",
    "bg-[#efe9dd]",
    "bg-white/70",
  ];

  const rightToneByIndex: string[] = [
    "bg-white/60",
    "bg-[#efe9dd]",
    "bg-white/60",
    "bg-[#efe9dd]",
    "bg-white/60",
  ];

  return (
    <MarketingEditorialShell
      title="Сценарии, в которых Steloom даёт прикладной юридический результат"
      description="Платформа подходит для M&A, due diligence, contract review, аудита и внутреннего расследования, когда нужен не общий summary, а проверяемый structured output."
    >
      <div className="grid gap-5">
        {items.map((item, index) => {
          const Icon = item.icon;
          const leftTone =
            leftToneByIndex[index] ??
            leftToneByIndex[leftToneByIndex.length - 1];
          const rightTone =
            rightToneByIndex[index] ??
            rightToneByIndex[rightToneByIndex.length - 1];

          return (
            <div
              key={item.title}
              className="grid gap-4 lg:grid-cols-12 lg:gap-5"
            >
              <div
                className={`rounded-[28px] border border-stone-900/10 p-6 lg:col-span-6 lg:p-7 ${leftTone}`}
              >
                <Icon className="h-5 w-5 text-stone-700" />
                <h2 className="mt-10 max-w-sm font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950">
                  {item.title}
                </h2>
                <p className="mt-4 max-w-lg text-sm leading-7 text-stone-700 lg:text-base">
                  {item.description}
                </p>
              </div>

              <div
                className={`rounded-[28px] border border-stone-900/10 p-6 lg:col-span-6 lg:p-7 ${rightTone}`}
              >
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                  Дополнительное описание
                </div>
                <p className="mt-10 max-w-lg text-sm leading-7 text-stone-700 lg:text-base">
                  Будет дополнено позже.
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </MarketingEditorialShell>
  );
};

export default SolutionsPage;