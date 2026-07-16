import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";
import {
  ArrowRight,
  FileSearch,
  TrendingUp,
  Layers,
  CheckCircle2,
  ShieldCheck,
} from "lucide-react";

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const LawFirmsPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1A1917] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <HowSteloomHelpsSection />
        <ScenariosSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default LawFirmsPage;

function HeroSection({ onDemo }: { onDemo: () => void }) {
  const prefersReduced = useReducedMotion();

  return (
    <section data-header-theme="light" className="bg-[#FAF8F5]">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <RevealItem>
            <PathCrumb root="Сценарии использования" leaf="Юридические фирмы" />
          </RevealItem>

          <RevealItem>
            <div className="mt-12 lg:w-1/2">
              <p className="text-[1.0625rem] leading-[1.75] text-[var(--text-secondary)] font-light">
                До 63% рабочего времени юриста уходит на рутинную обработку документов -
                вычитку, поиск отклонений и сортировку массивов. Steloom берёт эту рутину
                на себя: структурирует массив, применяет плейбуки фирмы ко всем документам
                и формирует прослеживаемые выводы.
              </p>
            </div>
          </RevealItem>

          <RevealItem>
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.3, ease }}
              className="mt-16 relative overflow-hidden rounded-none border border-[#E8E4DD] bg-white shadow-sm"
            >
              <img
                src="/lo-1.jpg"
                alt="Law Firm Workspace"
                className="block h-auto w-full object-cover"
              />
            </motion.div>
          </RevealItem>

          <RevealItem>
            <h1
              className="mt-20 lg:mt-32 font-serif tracking-[-0.03em] max-w-6xl"
              style={{
                fontSize: "clamp(2.5rem, 5vw, 4.2rem)",
                lineHeight: 1.05,
              }}
            >
              Рутину берёт на себя платформа - <br />
              <span className="italic font-light text-[var(--color-accent)]">
                решение остаётся за юристом.
              </span>
            </h1>
          </RevealItem>

          <RevealItem>
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                Запросить демонстрацию
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </RevealItem>
        </Reveal>
      </div>
    </section>
  );
}

function HowSteloomHelpsSection() {
  const results = [
    {
      image: "/lf-1-1.png",
      title: "Скорость и охват",
      text: "Сокращение времени проверки контракта с 2–4 часов до 20–40 минут. 100% охват массива - каждый документ проверен, ни один не выпал из анализа.",
    },
    {
      image: "/lf-1-2.png",
      title: "Качество и снижение пропусков",
      text: "Единые правила применяются ко всем документам. Система выявляет проблемные клаузулы и отклонения без зависимости от усталости юриста.",
    },
    {
      image: "/lf-1-3.png",
      title: "Прослеживаемость и доказательность",
      text: "Каждое заключение сопровождается ссылкой на конкретный абзац первоисточника. Готовая доказательная база для клиента или регулятора.",
    },
  ];

  return (
    <section data-header-theme="light" className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <RevealItem>
              <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
                Что получает юридическая фирма
              </p>
            </RevealItem>

          </div>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {results.slice(0, 3).map((item) => (
              <RevealItem key={item.title}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-[#E8E4DD]/40 bg-[var(--bg-surface)]">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6">
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>

          <div className="mt-24 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {results.slice(3).map((item) => (
              <RevealItem key={item.title}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-[#E8E4DD]/40 bg-[var(--bg-surface)]">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6">
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function ScenariosSection() {
  const scenarios = [
    {
      title: "Due diligence при M&A",
      text: "Сотни корпоративных документов, договоров и судебных дел за один прогон. Сводный отчёт с рисками и классификацией.",
    },
    {
      title: "Проверка контрагентов",
      text: "Анализ структуры владения, выявление аффилированности, флаггирование офшорных юрисдикций. Единый стандарт для каждого случая.",
    },
    {
      title: "Комплаенс-контроль договоров",
      text: "Применение внутренних плейбуков ко всему массиву. Выявление пропущенных обязательных условий и отклонений от типовых форм.",
    },
    {
      title: "Аудит договорного портфеля",
      text: "Структурирование массива, проверка по чек-листам, формирование аудиторского следа с прослеживаемостью до первоисточника.",
    },
  ];

  return (
    <section
      data-header-theme="dark"
      className="relative overflow-hidden border-t border-white/10 text-white"
    >
      <div
        className="absolute inset-0 bg-center bg-cover bg-no-repeat"
        style={{ backgroundImage: 'url("/lf-2-2.png")' }}
      />
      <div className="absolute inset-0 bg-[#111111]/78" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-black/35 to-black/55" />

      <div
        className="relative mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-white/55 font-medium mb-4">
            Сценарии применения
          </p>

          <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] tracking-[-0.02em] text-white mb-16">
            Где Steloom ускоряет работу фирмы
          </h2>

          <div className="space-y-0">
            {scenarios.map((item) => (
              <RevealItem key={item.title}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-8 border-t border-white/12">
                  <div className="md:col-span-4">
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-white italic">
                      {item.title}
                    </h3>
                  </div>
                  <div className="md:col-span-8">
                    <p className="text-[0.9375rem] leading-[1.7] text-white/72 font-light max-w-2xl">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CapabilitiesSection() {
  const capabilities = [
    {
      icon: Layers,
      title: "Структурирование массива",
      bullets: [
        "Автоматическая классификация по типам, датам, контрагентам",
        "Единое представление разнородных форматов (сканы, PDF, Word)",
        "Исключение ручной сортировки",
      ],
    },
    {
      icon: ShieldCheck,
      title: "Применение плейбуков",
      bullets: [
        "Сопоставление каждого договора с внутренними формами фирмы",
        "Выявление пропущенных обязательных условий и оговорок",
        "Флаггирование документов для суждения юриста",
      ],
    },
    {
      icon: FileSearch,
      title: "Аудиторский след",
      bullets: [
        "Каждое заключение связано с конкретным абзацем источника",
        "Полная история: что загружено, какие правила применены",
        "Экспортируемые отчёты для клиентских заключений",
      ],
    },
    {
      icon: TrendingUp,
      title: "Экономика фирмы",
      bullets: [
        "Меньше non-billable часов - больше времени на клиента",
        "Единый стандарт качества по всем проектам и командам",
        "Снижение зависимости от конкретного исполнителя",
      ],
    },
  ];

  return (
    <section data-header-theme="light" className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
            Что автоматизирует Steloom
          </p>
          <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] tracking-[-0.02em] text-[#1A1917] mb-16 max-w-none">
            Ключевые задачи фирмы - в едином потоке анализа
          </h2>
          <div className="mt-16">
            {capabilities.map((item) => (
              <RevealItem key={item.title}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4 flex items-center gap-4">
                    <item.icon className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-3">
                      {item.bullets.map((bullet) => (
                        <li key={bullet} className="flex items-start gap-3">
                          <CheckCircle2 className="mt-1 h-4 w-4 text-[var(--color-accent)] opacity-50" />
                          <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                            {bullet}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CTASection({ onDemo }: { onDemo: () => void }) {
  return (
    <section
      data-header-theme="light"
      className="bg-[#FAF8F5] py-28 lg:py-40 border-t border-[#E8E4DD]"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div
            className="mx-auto flex flex-col items-center text-center"
            style={{ maxWidth: 720 }}
          >
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />
            <h2 className="mt-10 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
              Меньше non-billable часов - <br />
              <span className="italic font-light opacity-60 text-[var(--color-accent)]">
                больше времени на клиента
              </span>
            </h2>
            <div className="mt-7 space-y-5 text-[1.0625rem] leading-[1.75] text-[#78756F]">
              <p>
                Steloom берёт на себя сканирование массива, первичный анализ и сопоставление с
                плейбуками - освобождая billable часы юристов для стратегии и работы с клиентом.
              </p>
              <p>
                Загрузите массив документов - Steloom применит ваши плейбуки, выделит отклонения
                и сформирует прослеживаемую доказательную базу.
              </p>
            </div>
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                Запросить демонстрацию <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="mt-8 text-[0.8125rem] leading-[1.6] text-[#A8A29E]">
              Обычно мы отвечаем в течение одного рабочего дня.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


