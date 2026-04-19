import React from "react";
import {
  ArrowRight,
  Cpu,
  FileText,
  GitBranch,
  Layers,
  Network,
  Sparkles,
} from "lucide-react";
import MarketingEditorialShell from "../components/marketing/landing/MarketingEditorialShell";
import { landingContent } from "../content/landingContent";

const TechOverviewPage: React.FC = () => {
  const { workflow } = landingContent;

  return (
    <MarketingEditorialShell
      eyebrow="Architecture"
      title="Технический обзор LegalMAS и document pipeline"
      description="Как устроен ingest, обработка и анализ сложных юридических массивов документов в LegalMAS: от загрузки и нормализации до сценарного вывода и интеграций."
      primaryLink={{ label: "Посмотреть capabilities", to: "/solutions" }}
      secondaryLink={{ label: "Открыть security", to: "/security" }}
    >
      {/* Pipeline summary + key points */}
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="rounded-[32px] border border-stone-900/10 bg-[#ece5d8] p-7 lg:col-span-5 lg:p-9">
          <div className="inline-flex items-center rounded-full bg-stone-900/5 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-stone-700">
            <GitBranch className="mr-2 h-3.5 w-3.5" />
            Document pipeline
          </div>
          <h2 className="mt-4 font-serif text-2xl tracking-[-0.03em] text-stone-950">
            От сырых файлов к структурированному юридическому слою
          </h2>
          <p className="mt-4 text-sm leading-7 text-stone-700">
            LegalMAS принимает scatter‑загрузку документов, нормализует их в едином
            pipeline и строит поверх стабильный слой юридически значимых сущностей,
            рисков и обязательств, пригодный для аудитов, DD и внутренних расследований.
          </p>
          <div className="mt-5 space-y-3 text-sm text-stone-800">
            <div className="flex items-start gap-2">
              <Layers className="mt-0.5 h-4 w-4 text-stone-600" />
              <span>
                Многоуровневый pipeline: ingest, canonicalization, layout, extraction, аналитика.
              </span>
            </div>
            <div className="flex items-start gap-2">
              <FileText className="mt-0.5 h-4 w-4 text-stone-600" />
              <span>
                Гибкая работа с data room и “грязными” архивами, без требований к структуре.
              </span>
            </div>
            <div className="flex items-start gap-2">
              <Cpu className="mt-0.5 h-4 w-4 text-stone-600" />
              <span>
                Комбинация deterministic‑правил и LLM, с audit‑friendly логированием шагов.
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
            <div className="rounded-2xl bg-[#f5eee2] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                Ingest
              </div>
              <p className="mt-2">
                Поддержка Dataroom, S3/MinIO, прямых загрузок, batch‑pipeline для исторических
                архивов, нормализация форматов и encoding.
              </p>
            </div>
            <div className="rounded-2xl bg-[#f5eee2] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                Processing
              </div>
              <p className="mt-2">
                Layout‑анализ, OCR при необходимости, language detection, chunking, entity‑layer
                и классификация документов по сценариям.
              </p>
            </div>
            <div className="rounded-2xl bg-[#f5eee2] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                Analytics
              </div>
              <p className="mt-2">
                Risk‑scoring, detection отклонений от стандартов, агрегированные view по сделкам,
                контрагентам и портфелям.
              </p>
            </div>
            <div className="rounded-2xl bg-[#f5eee2] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                Delivery
              </div>
              <p className="mt-2">
                UI‑слой для юристов, API/exports для внутренних систем, audit trail для
                compliance и проверяемости выводов.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 4-step workflow из главной, перенесён сюда */}
      <div className="mt-10 rounded-[32px] border border-stone-900/10 bg-[#f1ebdf] p-6 sm:p-8 lg:p-10">
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-4">
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Workflow
            </div>
            <h3 className="mt-4 max-w-md font-serif text-2xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-3xl">
              {workflow.title}
            </h3>
            <p className="mt-5 max-w-md text-sm leading-7 text-stone-700 lg:text-base">
              {workflow.subtitle}
            </p>
          </div>

          <div className="lg:col-span-8">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {workflow.steps.map((step, index) => {
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

      {/* Workflow steps — detailed 6-step pipeline */}
      <div className="mt-10 rounded-[32px] border border-stone-900/10 bg-white/70 p-6 sm:p-8 lg:p-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">
              Pipeline, шаг за шагом
            </div>
            <h3 className="mt-2 text-lg font-semibold text-stone-950">
              Как документ проходит через LegalMAS
            </h3>
          </div>
          <div className="inline-flex items-center rounded-full bg-stone-900/5 px-3 py-1 text-[11px] font-medium text-stone-700">
            <Network className="mr-1.5 h-3.5 w-3.5" />
            Orchestrated via Celery / workers
          </div>
        </div>

        <ol className="mt-6 grid gap-4 text-sm text-stone-800 md:grid-cols-2 lg:grid-cols-3">
          <li className="flex h-full flex-col rounded-2xl bg-[#f7f3ea] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-900 text-[11px] text-[#f7f3ea]">
                1
              </span>
              Ingest & normalization
            </div>
            <p className="mt-3">
              Прием файлов из разных источников, маппинг в internal модель документа, выравнивание
              названий, структур и метаданных.
            </p>
          </li>

          <li className="flex h-full flex-col rounded-2xl bg-[#f7f3ea] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-900 text-[11px] text-[#f7f3ea]">
                2
              </span>
              Layout, text, entities
            </div>
            <p className="mt-3">
              Извлечение текста, layout‑blocks, таблиц; NER, detection ключевых сущностей и
              структурирование по документ‑типам и разделам.
            </p>
          </li>

          <li className="flex h-full flex-col rounded-2xl bg-[#f7f3ea] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-900 text-[11px] text-[#f7f3ea]">
                3
              </span>
              Scenario‑level analytics
            </div>
            <p className="mt-3">
              Применение сценариев M&A/DD, contract review, расследований; построение risk‑view,
              checklist‑ответов и экспортируемых выводов.
            </p>
          </li>

          <li className="flex h-full flex-col rounded-2xl bg-[#f7f3ea] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-900 text-[11px] text-[#f7f3ea]">
                4
              </span>
              Storage & indexing
            </div>
            <p className="mt-3">
              Хранение артефактов обработки, версий, embeddings и audit‑лога в PostgreSQL + объектном
              хранилище, оптимизированное под повторное использование.
            </p>
          </li>

          <li className="flex h-full flex-col rounded-2xl bg-[#f7f3ea] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-900 text-[11px] text-[#f7f3ea]">
                5
              </span>
              Delivery & UX
            </div>
            <p className="mt-3">
              UI для юристов, API для внутренней инфраструктуры, экспорт структурированных findings и
              сохранение всех шагов для пересмотра.
            </p>
          </li>

          <li className="flex h-full flex-col rounded-2xl bg-[#f7f3ea] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-900 text-[11px] text-[#f7f3ea]">
                6
              </span>
              Feedback‑loop
            </div>
            <p className="mt-3">
              Возможность фиксировать правки юристов, поднимать их до уровня правил и промптов,
              постепенно повышая устойчивость pipeline к edge‑кейсам.
            </p>
          </li>
        </ol>

        <div className="mt-6 flex items-center justify-end text-sm text-stone-700">
          <ArrowRight className="mr-2 h-4 w-4" />
          <span>
            Детальная схема pipeline доступна в internal docs и может быть экспортирована клиенту.
          </span>
        </div>
      </div>
    </MarketingEditorialShell>
  );
};

export default TechOverviewPage;


