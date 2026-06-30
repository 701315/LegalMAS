// src/marketing/components/home/FaqSection.tsx

import React, { useState } from "react";

const FAQ_ITEMS = [
  {
    q: "Чем Steloom отличается от корпоративной базы знаний?",
    a: "База знаний хранит то, что вы сами туда положили. Steloom извлекает структурированное знание напрямую из документов — автоматически, с привязкой к источнику и в контексте вашего playbook. Это активный intelligence layer, а не пассивное хранилище.",
  },
  {
    q: "Можно ли работать с NDA-чувствительными документами?",
    a: "Да. Steloom поддерживает local-first режим с PII-gateway перед обращением к внешним моделям. Для чувствительных сценариев документы не покидают контур вашей инфраструктуры.",
  },
  {
    q: "Что если модель сделает ошибку — как мы это увидим?",
    a: "Каждый вывод привязан к конкретному источнику — пункту, странице и документу. Вы всегда видите, на чём основан результат. Steloom проектировался как аудитируемая система, а не black box.",
  },
  {
    q: "Как система работает с нестандартными структурами договоров?",
    a: "Steloom не опирается на жёсткие шаблоны структуры. Extraction работает на уровне смысла, а не форматирования. Нестандартные договоры и смешанные структуры обрабатываются корректно.",
  },
  {
    q: "Интеграция с DMS / iManage / SharePoint — сколько это займёт?",
    a: "Базовая интеграция через API — от 3 до 7 рабочих дней. На этапе демо разбираем ваш конкретный стек и даём реалистичные сроки.",
  },
  {
    q: "Насколько система адаптируется к нашему playbook?",
    a: "Playbook-конфигурация — это ядро продукта, а не опция. Steloom работает с вашими приоритетами проверки и вашей логикой флагирования рисков.",
  },
];

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[#E5E2DA] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-4 py-3.5 text-left"
      >
        <span className="text-sm font-medium leading-6 text-stone-900">{q}</span>
        <span
          className="mt-0.5 shrink-0 text-stone-400 transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
      </button>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 200 : 0, opacity: open ? 1 : 0 }}
      >
        <p className="pb-3.5 text-sm leading-7 text-stone-500">{a}</p>
      </div>
    </div>
  );
}

const FaqSection: React.FC = () => {
  return (
    <section
      className="flex items-center bg-[#F1EFEA]"
      style={{ height: "50vh", minHeight: 320 }}
    >
      <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 xl:px-12">
        <div className="grid gap-10 lg:grid-cols-[0.38fr_0.62fr] items-start">

          <div>
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              FAQ
            </div>
            <h2 className="mt-4 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-950 lg:text-[3.5rem]">
              Вопросы, которые задают до того, как пойти в пилот.
            </h2>
            <a
              href="mailto:hello@steloom.com"
              className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-[#2F5A4A] transition-colors hover:text-[#3F735F]"
            >
              Задать свой вопрос →
            </a>
          </div>

          <div className="overflow-y-auto" style={{ maxHeight: "calc(50vh - 48px)" }}>
            {FAQ_ITEMS.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>

        </div>
      </div>
    </section>
  );
};

export default FaqSection;

