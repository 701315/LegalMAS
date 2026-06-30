// src/marketing/components/home/ArchitecturePreviewSection.tsx

import React, { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, CheckCircle2 } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";

const STEPS = [
  {
    id: "ingest",
    label: "Document Ingestion",
    tag: "Шаг 01",
    headline: "Система принимает пакет документов и определяет тип и структуру каждого.",
    body: "SPA, SHA, Disclosure Letter, Employment Agreement — каждый документ разбирается на разделы, определения и перекрёстные ссылки. Формируется единая карта пакета сделки.",
    details: ["Определение типа документа", "Парсинг структуры и разделов", "Построение карты перекрёстных ссылок"],
  },
  {
    id: "playbook",
    label: "Playbook Analysis",
    tag: "Шаг 02",
    headline: "Каждое положение проверяется против применимого Playbook.",
    body: "Предустановленные или настраиваемые сценарии задают стандарт для каждого типа сделки. Отклонения фиксируются с точным указанием источника — документ, раздел, параграф.",
    details: ["Предустановленные и кастомные Playbook", "Выявление отклонений от стандартной позиции", "Привязка каждого вывода к источнику"],
  },
  {
    id: "output",
    label: "Structured Output",
    tag: "Шаг 03",
    headline: "Система формирует структурированный отчёт, готовый к передаче команде.",
    body: "Финальный вывод — таблица findings со статусами, risk-флагами и прямыми ссылками на источники. Каждый вывод верифицируем и воспроизводим.",
    details: ["Таблица findings с risk-статусами", "Source-linked выводы для верификации", "Export-ready формат"],
  },
];

const STEP_DURATION = 12000;

function PipelineVisual({
  activeStep,
  onStepClick,
}: {
  activeStep: number;
  onStepClick: (i: number) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      {STEPS.map((step, i) => {
        const isActive = i === activeStep;
        const isDone = i < activeStep;
        const isFuture = i > activeStep;

        return (
          <div
            key={step.id}
            onClick={() => onStepClick(i)}
            className="relative overflow-hidden rounded-[24px] border transition-all duration-700 cursor-pointer"
            style={{
              borderColor: isActive ? "#2F5A4A" : isDone ? "#E5E2DA" : "#EDEAE5",
              background: isActive ? "white" : isDone ? "#FAFAF9" : "#F8F7F4",
              boxShadow: isActive ? "0 4px 24px rgba(47,90,74,0.08)" : "none",
              opacity: isFuture ? 0.45 : 1,
            }}
          >
            <div className="flex items-start gap-4 px-6 pt-5 pb-4">
              <div
                className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-all duration-500"
                style={{
                  background: isActive ? "#111827" : isDone ? "#2F5A4A" : "#E8E5E0",
                  color: isActive || isDone ? "white" : "#A8A29E",
                }}
              >
                {isDone ? (
                  <CheckCircle2 size={13} strokeWidth={2.5} />
                ) : (
                  <span className="text-[11px] font-semibold">{i + 1}</span>
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2.5">
                  <span
                    className="text-[10px] font-medium uppercase tracking-[0.18em] transition-colors duration-500"
                    style={{ color: isActive ? "#2F5A4A" : "#A8A29E" }}
                  >
                    {step.tag}
                  </span>
                  <span className="text-stone-300">·</span>
                  <span
                    className="text-[11px] font-medium transition-colors duration-500"
                    style={{ color: isActive ? "#111827" : isDone ? "#78716C" : "#A8A29E" }}
                  >
                    {step.label}
                  </span>
                </div>

                <p
                  className="mt-2 font-serif leading-snug tracking-[-0.02em] transition-all duration-500"
                  style={{
                    fontSize: isActive ? "1.125rem" : "0.9375rem",
                    color: isActive ? "#111827" : isDone ? "#78716C" : "#A8A29E",
                  }}
                >
                  {step.headline}
                </p>
              </div>
            </div>

            <div
              className="overflow-hidden transition-all duration-700 ease-in-out"
              style={{ maxHeight: isActive ? "300px" : "0px", opacity: isActive ? 1 : 0 }}
            >
              <div className="px-6 pb-6 pl-[4.25rem]">
                <p className="text-sm leading-7 text-stone-500">{step.body}</p>
                <ul className="mt-3 space-y-2">
                  {step.details.map((d) => (
                    <li key={d} className="flex items-center gap-2.5">
                      <div className="h-1 w-1 shrink-0 rounded-full bg-[#2F5A4A]" />
                      <span className="text-sm leading-6 text-stone-400">{d}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {isActive && (
              <div className="absolute bottom-0 left-0 right-0 h-[2px] overflow-hidden bg-[#F0EDE8]">
                <div
                  key={`${activeStep}-progress`}
                  className="h-full bg-[#2F5A4A]"
                  style={{ animation: `progressFill ${STEP_DURATION}ms linear forwards` }}
                />
              </div>
            )}
          </div>
        );
      })}

      <style>{`
        @keyframes progressFill {
          from { width: 0%; }
          to   { width: 100%; }
        }
      `}</style>
    </div>
  );
}

const PRINCIPLES = [
  {
    label: "Consistency",
    text: "Один playbook применяется ко всему пакету документов, а не к одному чату.",
  },
  {
    label: "Control",
    text: "От ingestion до output каждый шаг наблюдаем, тестируем и управляем.",
  },
  {
    label: "Scale",
    text: "Пайплайн адаптируется под разные сделки без разрозненных prompt-паттернов.",
  },
];

const ArchitecturePreviewSection: React.FC = () => {
  const [activeStep, setActiveStep] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const left = useScrollReveal(0);
  const right = useScrollReveal(120);

  const startAutoPlay = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      setActiveStep((s) => (s + 1) % STEPS.length);
    }, STEP_DURATION);
  };

  useEffect(() => {
    startAutoPlay();
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  const handleStepClick = (i: number) => {
    setActiveStep(i);
    startAutoPlay();
  };

  return (
    <section
      id="architecture"
      className="relative flex min-h-screen items-center bg-[#F8F7F4] py-20 scroll-mt-0"
    >
      <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 xl:px-12">
        <div className="grid items-center gap-16 lg:grid-cols-2">

          {/* ── Левая колонка ── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="flex flex-col justify-center"
          >
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Архитектура
            </div>
            <h2 className="mt-5 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-950 lg:text-[3.5rem]">
              Пайплайн,
              <br />
              а не промпт.
            </h2>
            <p className="mt-5 max-w-md text-base leading-8 text-stone-600">
              Steloom обрабатывает документы через воспроизводимый pipeline —
              каждый шаг детерминирован, наблюдаем и привязан к источнику.
              Не разовый чат, а управляемый процесс.
            </p>

            <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
              {PRINCIPLES.map((p) => (
                <div
                  key={p.label}
                  className="rounded-2xl border border-[#E5E2DA] bg-white px-5 py-5"
                >
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-400">
                    {p.label}
                  </p>
                  <p className="mt-3 text-sm leading-7 text-stone-600">
                    {p.text}
                  </p>
                </div>
              ))}
            </div>

            <Link
              to="/tech#pipeline"
              className="mt-8 inline-flex w-fit items-center gap-2 rounded-full border border-[#E5E2DA] bg-white px-5 py-2.5 text-sm font-medium text-stone-700 transition-all hover:border-stone-300 hover:text-stone-950"
            >
              Подробнее об архитектуре
              <ArrowUpRight size={14} />
            </Link>
          </div>

          {/* ── Правая колонка ── */}
          <div ref={right.ref as React.Ref<HTMLDivElement>} style={right.style}>
            <PipelineVisual activeStep={activeStep} onStepClick={handleStepClick} />
          </div>

        </div>
      </div>
    </section>
  );
};

export default ArchitecturePreviewSection;

