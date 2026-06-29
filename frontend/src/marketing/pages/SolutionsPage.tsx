import React from "react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { landingContent } from "../content/landingContent";
import { SearchCheck } from "lucide-react";

const SolutionsPage: React.FC = () => {
  const { useCases } = landingContent;

  const extendedUseCases = [
    ...useCases.items,
    {
      icon: SearchCheck,
      title: "Проверка активов \\ партнеров",
      description:
        "Проведение дополнительной проверки активов \\ контрагентов из анализируемых документов по выбранным критериям через сторонние сервисы и агрегирование результатов их проверки в основной отчет.",
    },
  ];

  // Схема цветов для левого блока по порядку сценариев
  const leftToneByIndex: string[] = [
    "bg-white/70",      // 1. M&A и Due Diligence
    "bg-[#efe9dd]",     // 2. Корпоративные правовые отделы (бежевый)
    "bg-white/75",      // 3. Контрактный review (белый)
    "bg-[#efe9dd]",     // 4. Аудит и расследования (бежевый)
    "bg-white/70",      // 5. Проверка активов \ партнеров (белый)
  ];

  // Для правых блоков: по умолчанию белый, но те, что напротив
  // "Корпоративные правовые отделы" и "Аудит и расследования" — бежевые
  const rightToneByIndex: string[] = [
    "bg-white/60",      // 1. M&A
    "bg-[#efe9dd]",     // 2. Корпоративные правовые отделы (бежевый)
    "bg-white/60",      // 3. Контрактный review
    "bg-[#efe9dd]",     // 4. Аудит и расследования (бежевый)
    "bg-white/60",      // 5. Проверка активов \ партнеров
  ];

  return (
    <MarketingEditorialShell
      eyebrow="Solutions"
      title="Сценарии, в которых LegalMAS даёт прикладной юридический результат"
      description="Платформа подходит для M&A, due diligence, contract review, аудита и внутреннего расследования, когда нужен не общий summary, а проверяемый structured output."
      primaryLink={{ label: "Открыть возможности", to: "/capabilities" }}
      secondaryLink={{ label: "Посмотреть security", to: "/security" }}
    >
      <div className="grid gap-5">
        {extendedUseCases.map((item, index) => {
          const Icon = item.icon;
          const leftTone =
            leftToneByIndex[index] ?? leftToneByIndex[leftToneByIndex.length - 1];
          const rightTone =
            rightToneByIndex[index] ?? rightToneByIndex[rightToneByIndex.length - 1];

          return (
            <div
              key={item.title}
              className="grid gap-4 lg:grid-cols-12 lg:gap-5"
            >
              {/* Левый блок сценария */}
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

              {/* Правый блок описания */}
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


