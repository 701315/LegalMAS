// src/marketing/pages/CapabilitiesPage.tsx

import React from "react";
import {
  Cpu,
  FileText,
  GitBranch,
  Layers,
  Network,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { landingContent } from "../content/landingContent";

const CapabilitiesPage: React.FC = () => {
  const { capabilities, architecturePreview } = landingContent;

  return (
    <MarketingEditorialShell
      title="Платформа Steloom: возможности и архитектура"
      description="Что платформа делает для юридических команд — и как она устроена внутри: от playbook-driven review до document pipeline и structured output."
    >
      {/* ════════════════════════════════════════════════════════════════════════
          БЛОК 1 — ВОЗМОЖНОСТИ
          ════════════════════════════════════════════════════════════════════════ */}

      <div className="grid gap-5 lg:grid-cols-12">
        {capabilities.featured.map((item, idx) => {
          const Icon = item.icon;

          return (
            <div
              key={item.title}
              className={`rounded-[32px] border border-stone-900/10 p-7 lg:p-9 ${
                idx === 0
                  ? "bg-[#ece5d8] lg:col-span-7"
                  : "bg-white/70 lg:col-span-5"
              }`}
            >
              <Icon className="h-6 w-6 text-stone-700" />
              <h2 className="mt-10 max-w-xl font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-[2.3rem]">
                {item.title}
              </h2>
              <p className="mt-5 text-base leading-8 text-stone-700">
                {item.description}
              </p>
            </div>
          );
        })}

        {capabilities.support.map((item) => {
          const Icon = item.icon;

          return (
            <div
              key={item.title}
              className="rounded-[28px] border border-stone-900/10 bg-white/65 p-6 lg:col-span-4"
            >
              <Icon className="h-5 w-5 text-stone-700" />
              <h3 className="mt-8 text-xl font-semibold text-stone-950">
                {item.title}
              </h3>
              <p className="mt-3 text-sm leading-7 text-stone-700">
                {item.description}
              </p>
            </div>
          );
        })}
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          БЛОК 2 — АРХИТЕКТУРА И PIPELINE
          ════════════════════════════════════════════════════════════════════════ */}

      <div className="mt-16">
        <div className="mb-10">
          <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
            Архитектура
          </div>
          <h2 className="mt-4 max-w-3xl font-serif text-4xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-5xl">
            Как устроен Steloom внутри
          </h2>
          <p className="mt-5 max-w-3xl text-base leading-8 text-stone-600 lg:text-[1.05rem]">
            Технический обзор document pipeline: от загрузки и нормализации до
            сценарного вывода и интеграций.
          </p>
        </div>

        {/* Pipeline summary + architecture layers */}
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="rounded-[32px] border border-stone-900/10 bg-[#ece5d8] p-7 lg:col-span-5 lg:p-9">
            <div className="inline-flex items-center rounded-full bg-stone-900/5 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-stone-700">
              <GitBranch className="mr-2 h-3.5 w-3.5" />
              Document pipeline
            </div>
            <h3 className="mt-4 font-serif text-2xl tracking-[-0.03em] text-stone-950">
              От сырых файлов к структурированному юридическому слою
            </h3>
            <p className="mt-4 text-sm leading-7 text-stone-700">
              Steloom принимает scatter-загрузку документов, нормализует их в
              едином pipeline и строит поверх стабильный слой юридически значимых
              сущностей, рисков и обязательств, пригодный для аудитов, DD и
              внутренних расследований.
            </p>
            <div className="mt-5 space-y-3 text-sm text-stone-800">
              <div className="flex items-start gap-2">
                <Layers className="mt-0.5 h-4 w-4 text-stone-600" />
                <span>
                  Многоуровневый pipeline: ingest, canonicalization, layout,
                  extraction, аналитика.
                </span>
              </div>
              <div className="flex items-start gap-2">
                <FileText className="mt-0.5 h-4 w-4 text-stone-600" />
                <span>
                  Гибкая работа с data room и «грязными» архивами, без
                  требований к структуре.
                </span>
              </div>
              <div className="flex items-start gap-2">
                <Cpu className="mt-0.5 h-4 w-4 text-stone-600" />
                <span>
                  Комбинация deterministic-правил и LLM, с audit-friendly
                  логированием шагов.
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-[32px] border border-stone-900/10 bg-white/70 p-7 lg:col-span-7 lg:p-9">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                  Слои архитектуры
                </div>
                <h3 className="mt-2 text-lg font-semibold text-stone-950">
                  Ingest, processing, analytics, delivery
                </h3>
              </div>
              <div className="inline-flex items-center rounded-full bg-stone-900/5 px-3 py-1 text-[11px] font-medium text-stone-700">
                <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                LLM-native, but not LLM-only
              </div>
            </div>

            <div className="mt-5 grid gap-4 text-sm text-stone-800 sm:grid-cols-2">
              {[
                {
                  label: "Ingest",
                  text: "Поддержка Dataroom, S3/MinIO, прямых загрузок, batch-pipeline для исторических архивов, нормализация форматов и encoding.",
                },
                {
                  label: "Processing",
                  text: "Layout-анализ, OCR при необходимости, language detection, chunking, entity-layer и классификация документов по сценариям.",
                },
                {
                  label: "Analytics",
                  text: "Risk-scoring, detection отклонений от стандартов, агрегированные view по сделкам, контрагентам и портфелям.",
                },
                {
                  label: "Delivery",
                  text: "UI-слой для юристов, API/exports для внутренних систем, audit trail для compliance и проверяемости выводов.",
                },
              ].map((block) => (
                <div key={block.label} className="rounded-2xl bg-[#f5eee2] p-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                    {block.label}
                  </div>
                  <p className="mt-2">{block.text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 4-step workflow */}
        <div className="mt-10 rounded-[32px] border border-stone-900/10 bg-[#f1ebdf] p-6 sm:p-8 lg:p-10">
          <div className="grid gap-10 lg:grid-cols-12 lg:gap-12">
            <div className="lg:col-span-4">
              <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
                Workflow
              </div>
              <h3 className="mt-4 max-w-md font-serif text-2xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-3xl">
                {architecturePreview.title}
              </h3>
              <p className="mt-5 max-w-md text-sm leading-7 text-stone-700 lg:text-base">
                {architecturePreview.description}
              </p>
            </div>

            <div className="lg:col-span-8">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {architecturePreview.steps.map((step, index) => {
                  const Icon = step.icon;

                  return (
                    <div
                      key={step.title}
                      className="flex h-full flex-col rounded-[28px] border border-stone-900/10 bg-[#f7f3ea] p-6"
                    >
                      <div className="flex items-center justify-between">
                        <Icon className="h-5 w-5 text-stone-700" />
                        <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">
                          {`0${index + 1}`}
                        </div>
                      </div>
                      <h4 className="mt-10 font-serif text-xl tracking-[-0.02em] text-stone-950">
                        {step.title}
                      </h4>
                      <p className="mt-4 text-sm leading-7 text-stone-700">
                        {step.text}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Detailed 6-step pipeline */}
        <div className="mt-10 rounded-[32px] border border-stone-900/10 bg-white/70 p-6 sm:p-8 lg:p-10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">
                Pipeline, шаг за шагом
              </div>
              <h3 className="mt-2 text-lg font-semibold text-stone-950">
                Как документ проходит через Steloom
              </h3>
            </div>
            <div className="inline-flex items-center rounded-full bg-stone-900/5 px-3 py-1 text-[11px] font-medium text-stone-700">
              <Network className="mr-1.5 h-3.5 w-3.5" />
              Orchestrated pipeline
            </div>
          </div>

          <ol className="mt-6 grid gap-4 text-sm text-stone-800 md:grid-cols-2 lg:grid-cols-3">
            {[
              {
                step: "1",
                label: "Загрузка и нормализация",
                text: "Приём файлов из разных источников, маппинг в internal модель документа, выравнивание названий, структур и метаданных.",
              },
              {
                step: "2",
                label: "Layout, текст, сущности",
                text: "Извлечение текста, layout-blocks, таблиц; NER, detection ключевых сущностей и структурирование по документ-типам и разделам.",
              },
              {
                step: "3",
                label: "Сценарная аналитика",
                text: "Применение сценариев M&A/DD, contract review, расследований; построение risk-view, checklist-ответов и экспортируемых выводов.",
              },
              {
                step: "4",
                label: "Хранение и индексация",
                text: "Хранение артефактов обработки, версий, embeddings и audit-лога в PostgreSQL + объектном хранилище, оптимизированное под повторное использование.",
              },
              {
                step: "5",
                label: "Доставка и UX",
                text: "UI для юристов, API для внутренней инфраструктуры, экспорт структурированных findings и сохранение всех шагов для пересмотра.",
              },
              {
                step: "6",
                label: "Feedback-loop",
                text: "Возможность фиксировать правки юристов, поднимать их до уровня правил и промптов, постепенно повышая устойчивость pipeline к edge-кейсам.",
              },
            ].map((item) => (
              <li
                key={item.step}
                className="flex h-full flex-col rounded-2xl bg-[#f7f3ea] p-4"
              >
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-900 text-[11px] text-[#f7f3ea]">
                    {item.step}
                  </span>
                  {item.label}
                </div>
                <p className="mt-3">{item.text}</p>
              </li>
            ))}
          </ol>

          <div className="mt-6 flex items-center justify-end text-sm text-stone-700">
            <ArrowRight className="mr-2 h-4 w-4" />
            <span>
              Детальная схема pipeline доступна в internal docs и может быть
              экспортирована клиенту.
            </span>
          </div>
        </div>
      </div>
    </MarketingEditorialShell>
  );
};

export default CapabilitiesPage;


