// src/marketing/pages/SolutionsPage.tsx
import React, { useState } from "react";
import { ArrowRight } from "lucide-react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { useContactModal } from "../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface AudienceItem {
  title: string;
  intro: string;
  body: string;
  bullets: string[];
  outcome: string;
}

interface UseCaseItem {
  title: string;
  body: string;
  bullets: string[];
}

interface EnrichmentDirection {
  title: string;
  body: string;
  capabilities: string[];
  sources: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Content
// ─────────────────────────────────────────────────────────────────────────────

const AUDIENCE_ITEMS: AudienceItem[] = [
  {
    title: "M&A и Due Diligence",
    intro:
      "Чем больше data room, тем сложнее сохранить единый стандарт проверки. Разные юристы замечают разные риски, выводы оказываются в разных таблицах, а переход от итогового замечания к конкретному положению договора требует времени. При этом сроки сделки не позволяют проверять каждый документ вручную.",
    body: "Steloom работает со всей data room как с единым массивом документов, а не как с набором независимых файлов. Платформа автоматически классифицирует документы по типам, применяет к каждому соответствующий сценарий анализа и формирует структурированный DD grid по всему проекту.",
    bullets: [
      "Анализировать data room по единым правилам независимо от объема",
      "Автоматически применять разные сценарии проверки к разным типам документов",
      "Получать DD grid с привязкой findings к источникам",
      "Переходить от итогового замечания непосредственно к соответствующему положению документа",
    ],
    outcome:
      "В результате команда получает единый стандарт проверки по всему проекту и быстрее переходит от общего отчета к подтвержденным выводам по каждому документу.",
  },
  {
    title: "Юридические фирмы",
    intro:
      "Когда одновременно ведется несколько проектов, становится все сложнее масштабировать экспертизу команды. Внутренние стандарты и корпоративный playbook существуют, но их последовательное применение требует значительного времени и зависит от опыта конкретных юристов. Чем больше проектов, тем выше риск расхождения в качестве анализа.",
    body: "Steloom автоматизирует первичный этап анализа, позволяет применять корпоративный playbook ко всем проектам и формирует findings, пригодные для клиентских рекомендаций и юридических заключений.",
    bullets: [
      "Ускорять первичный review, сохраняя единый стандарт анализа",
      "Применять корпоративный playbook ко всем проектам и клиентам",
      "Получать структурированные findings для подготовки клиентских отчетов и рекомендаций",
      "Тратить меньше времени на повторяющиеся проверки и больше — на юридическую оценку и консультирование",
    ],
    outcome:
      "В результате фирма получает более масштабируемый процесс проверки документов, в котором качество анализа меньше зависит от конкретного исполнителя.",
  },
  {
    title: "Корпоративные юридические департаменты",
    intro:
      "Корпоративные юридические департаменты одновременно сопровождают закупки, продажи, HR, коммерческие проекты и внутренние корпоративные процессы. При увеличении количества договоров становится сложнее обеспечивать единый стандарт проверки и быстро выявлять отклонения от внутренних требований.",
    body: "Steloom позволяет автоматически применять внутренние стандарты организации, выявлять отклонения от корпоративного playbook и формировать проверяемые результаты для согласования и принятия решений.",
    bullets: [
      "Проверять договоры по корпоративному playbook",
      "Быстро находить отклонения от принятых позиций и стандартных формулировок",
      "Получать findings, которые можно использовать при согласовании с бизнесом и руководством",
      "Обеспечивать единый стандарт проверки в масштабах всего юридического департамента",
    ],
    outcome:
      "В результате департамент получает более последовательный процесс review и более прозрачную основу для согласования договоров и управления рисками.",
  },
  {
    title: "Внутренний аудит и compliance",
    intro:
      "Внутренний аудит регулярно проверяет большие массивы действующих и исторических договоров. По мере роста объема документов ручная проверка становится все более трудоемкой, а результаты сложно воспроизвести при повторной проверке или внешнем аудите. При этом важно не только найти отклонения, но и показать прозрачную историю того, как именно был проведен анализ.",
    body: "Steloom обеспечивает последовательную проверку документов по единым правилам и формирует структурированные findings с полной прослеживаемостью каждого вывода.",
    bullets: [
      "Проверять договорный массив на соответствие внутренним требованиям",
      "Выявлять отсутствующие или нетипичные положения",
      "Формировать воспроизводимую историю findings для compliance review",
      "Использовать результаты как прозрачную основу для внутреннего и внешнего контроля",
    ],
    outcome:
      "В результате команда получает более управляемый процесс проверки, в котором выводы можно повторно проверить, обосновать и использовать в дальнейшей работе.",
  },
];

const USE_CASES: UseCaseItem[] = [
  {
    title: "Due Diligence",
    body: "Steloom позволяет работать со всей data room как с единым массивом документов, а не как с набором отдельных файлов. Платформа классифицирует документы по типам, применяет к каждому релевантный сценарий анализа и собирает результаты в DD grid по ключевым рискам, отклонениям и существенным условиям.",
    bullets: [
      "Анализ полного пакета документов сделки по единым правилам",
      "Автоматическая классификация и типоспецифичный анализ",
      "DD grid по категориям документов и findings",
      "Привязка каждого вывода к документу, разделу и положению",
    ],
  },
  {
    title: "Contract Review",
    body: "Steloom используется для проверки отдельных договоров и больших пакетов контрактов по единым правилам. Платформа выделяет отклонения от стандартных позиций, отсутствующие положения и рискованные формулировки, при этом каждый вывод остается связанным с исходным положением договора.",
    bullets: [
      "Ускорение первичного review документов",
      "Поиск отклонений от корпоративного playbook и стандартных формулировок",
      "Единый формат findings по всем документам проекта",
      "Быстрый переход от summary к конкретному фрагменту договора",
    ],
  },
  {
    title: "Проверка по внутренним стандартам",
    body: "Steloom дает возможность применять внутренние стандарты проверки последовательно ко всем документам. Команда может использовать разные сценарии анализа для разных типов документов, а также глобальные правила, применимые ко всему пакету.",
    bullets: [
      "Применение корпоративного playbook к каждому документу",
      "Использование разных сценариев проверки для разных типов документов",
      "Выявление отклонений от утвержденных формулировок",
      "Единый стандарт анализа независимо от исполнителя",
    ],
  },
  {
    title: "Внутренний аудит и проверка архивов",
    body: "Steloom используется не только для текущих сделок, но и для работы с существующим договорным массивом. Платформа позволяет проверять исторические документы на соответствие внутренним требованиям и формировать проверяемую историю анализа.",
    bullets: [
      "Обзор рисков по массиву действующих и архивных договоров",
      "Выявление отсутствующих или нетипичных условий",
      "Структурированная история findings для audit и compliance review",
      "Воспроизводимый процесс проверки по единым правилам",
    ],
  },
  {
    title: "Контроль замечаний и открытых условий по проекту",
    body: "Steloom позволяет команде отслеживать статус ключевых замечаний и открытых вопросов в рамках проекта. Findings остаются связанными с документами, участниками проекта и статусом рассмотрения, что упрощает координацию и ускоряет принятие решений.",
    bullets: [
      "Единое пространство для работы с замечаниями",
      "Понимание, какие вопросы закрыты, а какие требуют внимания",
      "Прозрачный переход от finding к положению документа",
      "Основа для эскалации и согласования внутри команды",
    ],
  },
];

const ENRICHMENT_DIRECTIONS: EnrichmentDirection[] = [
  {
    title: "Анализ контрагентов",
    body: "Steloom автоматически выявляет контрагентов в тексте, таблицах и приложениях документов сделки, формирует единый реестр по проекту и обогащает профиль каждой компании через внешние и внутренние источники данных. Результаты enrichment привязаны к исходным документам: команда видит, в каких контрактах и в какой роли фигурирует контрагент, и может оценить совокупную экспозицию в контексте сделки.",
    capabilities: [
      "Автоматическое выявление контрагентов по всему пакету документов",
      "Единый реестр с указанием роли, контрактов и совокупной суммы",
      "Risk aggregation: санкции, банкротство, суды, ownership и UBO",
      "Карточка контрагента с финансовым и ownership-контекстом",
      "Приоритизация критичных контрагентов для эскалации",
      "DD grid по контрагентам с привязкой findings к документам сделки",
    ],
    sources: [
      "Глобальные провайдеры: Orbis, D&B, OpenCorporates",
      "Локальные реестры: DED, MERSIS, коммерческие регистры",
      "Внутренние источники: ERP, vendor master, compliance DB",
    ],
  },
  {
    title: "Анализ недвижимого имущества",
    body: "Steloom выявляет объекты недвижимости в документах сделки — адреса, кадастровые номера, площади и описания — и формирует реестр активов по проекту. Каждый объект сопоставляется с данными внешних реестров и внутренней базы активов компании. Команда получает рабочий интерфейс для проверки прав, обременений и реестрового статуса с привязкой к исходным документам.",
    capabilities: [
      "Автоматическое выявление объектов недвижимости в документах",
      "Реестровая верификация: ЕГРН, DLD, национальные property registries",
      "Проверка обременений: ипотека, арест, сервитут",
      "Legal checks: title chain, registry match, zoning / land use",
      "Карточка объекта с registry snapshot и документными ссылками",
      "Единый реестр активов по всему проекту с risk-приоритизацией",
    ],
    sources: [
      "Россия: ЕГРН, публичная кадастровая карта",
      "UAE: Dubai Land Department, emirate land registries",
      "Европа: национальные land / property registries",
      "Внутренние базы: asset register, lease register, legal archive",
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Subcomponents
// ─────────────────────────────────────────────────────────────────────────────

/** Bullet list — паттерн SecurityFoundationSection */
function BulletList({
  items,
  dotColor = "bg-[#C86B52]",
}: {
  items: string[];
  dotColor?: string;
}) {
  return (
    <ul className="mt-5 space-y-3">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-4 text-[#78756F]">
          <span
            className={`mt-2.5 flex h-1.5 w-1.5 shrink-0 rounded-full ${dotColor}`}
            aria-hidden="true"
          />
          <span className="text-[0.9375rem] leading-[1.7]">{item}</span>
        </li>
      ))}
    </ul>
  );
}

/** Bullet list for dark backgrounds */
function BulletListInverse({ items }: { items: string[] }) {
  return (
    <ul className="mt-5 space-y-3">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-4 text-[#D6D0C7]">
          <span
            className="mt-2.5 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[#C86B52]"
            aria-hidden="true"
          />
          <span className="text-[0.9375rem] leading-[1.7]">{item}</span>
        </li>
      ))}
    </ul>
  );
}

/** Audience accordion item — паттерн FaqSection / FaqItem */
function AudienceAccordionItem({ item }: { item: AudienceItem }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-[#E8E4DD] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-4 py-6 text-left transition-colors hover:bg-[#FAF8F5]"
        aria-expanded={open}
      >
        <span className="font-serif text-[1.375rem] leading-tight tracking-[-0.02em] text-[#1A1917]">
          {item.title}
        </span>
        <span
          className="mt-1.5 shrink-0 text-[#A8A29E] transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
          aria-hidden="true"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
      </button>

      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 800 : 0, opacity: open ? 1 : 0 }}
      >
        <div className="pb-8 pr-8">
          <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
            {item.intro}
          </p>
          <p className="mt-4 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            {item.body}
          </p>
          <div className="mt-6">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#78756F]">
              С помощью Steloom команда может
            </p>
            <BulletList items={item.bullets} />
          </div>
          <p className="mt-6 rounded-xl bg-[#F3F0EB] px-5 py-4 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            {item.outcome}
          </p>
        </div>
      </div>
    </div>
  );
}

/** Use-case card — полная ширина, чередующийся фон */
function UseCaseCard({
  item,
  index,
}: {
  item: UseCaseItem;
  index: number;
}) {
  const isEven = index % 2 === 0;
  const bg = isEven ? "bg-white" : "bg-[#F3F0EB]";

  return (
    <div className={`rounded-2xl border border-[#E8E4DD] p-6 lg:p-8 ${bg}`}>
      <div className="grid gap-8 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-7">
          <h3 className="font-serif text-[1.5rem] leading-tight tracking-[-0.03em] text-[#1A1917]">
            {item.title}
          </h3>
          <p className="mt-4 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            {item.body}
          </p>
        </div>
        <div className="lg:col-span-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#78756F]">
            Типичные задачи
          </p>
          <BulletList items={item.bullets} />
        </div>
      </div>
    </div>
  );
}

/** Enrichment direction accordion — on dark background */
function EnrichmentAccordionItem({ item }: { item: EnrichmentDirection }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-white/10 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-4 py-6 text-left transition-colors hover:bg-white/[0.03]"
        aria-expanded={open}
      >
        <span className="font-serif text-[1.375rem] leading-tight tracking-[-0.02em] text-white">
          {item.title}
        </span>
        <span
          className="mt-1.5 shrink-0 text-[#A8A29E] transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
          aria-hidden="true"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
      </button>

      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 900 : 0, opacity: open ? 1 : 0 }}
      >
        <div className="pb-8 pr-8">
          <p className="text-[0.9375rem] leading-[1.7] text-[#D6D0C7]">
            {item.body}
          </p>

          <div className="mt-6">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#A8A29E]">
              Возможности платформы
            </p>
            <BulletListInverse items={item.capabilities} />
          </div>

          <div className="mt-6 rounded-xl bg-white/[0.06] px-5 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#A8A29E]">
              Источники данных
            </p>
            <BulletListInverse items={item.sources} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

const SolutionsPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <MarketingEditorialShell
      title="От одного договора до полной data room — единый процесс анализа, единые правила, проверяемый результат"
      description="Независимо от того, проверяете ли вы один договор, готовите юридическое заключение или проводите due diligence крупной сделки, Steloom объединяет все этапы проверки документов в единый воспроизводимый процесс анализа. Платформа автоматически определяет тип документа, применяет соответствующие правила проверки и формирует структурированные findings с привязкой к источникам — сохраняя единый стандарт работы при любом объеме документов."
    >
      {/* ── Hero CTA (Блок 1) ────────────────────────────────────────────── */}
      <div className="mb-16 flex flex-wrap gap-3 lg:mb-20">
        <button
          type="button"
          onClick={openContactModal}
          className="cta-primary"
        >
          Запросить демонстрацию
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={openContactModal}
          className="cta-secondary"
        >
          Связаться с командой
        </button>
      </div>

      {/* ── Блок 2: Для кого ─────────────────────────────────────────────── */}
      <div className="mb-16 lg:mb-20">
        <div className="mb-8">
          <div className="eyebrow">Для кого</div>
          <h2 className="mt-4 font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Для каких команд создана платформа
          </h2>
        </div>

        <div className="rounded-2xl border border-[#E8E4DD] bg-white px-6 lg:px-8">
          {AUDIENCE_ITEMS.map((item) => (
            <AudienceAccordionItem key={item.title} item={item} />
          ))}
        </div>
      </div>

      {/* ── Блок 3: Сценарии ─────────────────────────────────────────────── */}
      <div className="mb-16 lg:mb-20">
        <div className="mb-8">
          <div className="eyebrow">Сценарии</div>
          <h2 className="mt-4 font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Какие задачи решает Steloom
          </h2>
        </div>

        <div className="grid gap-5">
          {USE_CASES.map((item, index) => (
            <UseCaseCard key={item.title} item={item} index={index} />
          ))}
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════════
          Блок «Расширенный анализ» — тёмный, выделенный
          Паттерн: SecurityPage dark card (bg-[#1A1917])
          ══════════════════════════════════════════════════════════════════════ */}
      <div className="mb-16 lg:mb-20">
        <div className="rounded-2xl border border-[#E8E4DD] bg-[#1A1917] p-7 lg:p-10">
          {/* Section header */}
          <div className="mb-8">
            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#A8A29E]">
              Расширенный анализ
            </div>
            <h2 className="mt-4 max-w-3xl font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-white">
              Дополнительная проверка через внешние и внутренние источники данных
            </h2>
            <p className="mt-5 max-w-3xl text-[0.9375rem] leading-[1.7] text-[#D6D0C7]">
              Если сценарий проекта требует дополнительной проверки активов,
              контрагентов или связанных лиц, Steloom формирует связанный слой
              анализа на основе документов сделки и данных из внешних
              и внутренних источников. Результаты enrichment привязаны
              к исходным документам и встроены в общий рабочий процесс команды.
            </p>
          </div>

          {/* Accordion with two directions */}
          <div className="rounded-xl border border-white/10 bg-white/[0.04] px-6 lg:px-8">
            {ENRICHMENT_DIRECTIONS.map((item) => (
              <EnrichmentAccordionItem key={item.title} item={item} />
            ))}
          </div>

          {/* Summary note */}
          <div className="mt-8 flex flex-wrap gap-2.5">
            {[
              "Привязка к документам сделки",
              "Глобальные и локальные провайдеры",
              "Внутренние источники компании",
              "Risk aggregation",
              "Рабочее пространство для команды",
            ].map((badge) => (
              <div
                key={badge}
                className="rounded-full border border-white/10 bg-white/[0.06] px-3.5 py-2 text-xs font-medium text-[#D6D0C7]"
              >
                {badge}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Блок 4: CTA ──────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-7 lg:p-10">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Посмотрите, как Steloom решает задачи вашей команды
          </h2>
          <p className="mt-5 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Во время демонстрации мы покажем, как платформа работает с
            документами в сценарии, наиболее близком к вашим задачам: due
            diligence, contract review, проверка по корпоративному playbook или
            внутренний аудит.
          </p>
          <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Если у вас есть собственные договоры или материалы сделки, их
            можно использовать в качестве примера. Это позволит оценить работу
            платформы в условиях, максимально приближенных к реальным проектам
            вашей команды.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={openContactModal}
              className="cta-primary"
            >
              Запросить демонстрацию
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={openContactModal}
              className="cta-secondary"
            >
              Связаться с командой
            </button>
          </div>
          <p className="mt-5 text-[0.8125rem] text-[#A8A29E]">
            Среднее время демонстрации: 30–45 минут · Формат: онлайн или очно
          </p>
        </div>
      </div>

      {/* ── Финальная фраза ──────────────────────────────────────────────── */}
      <p className="mt-10 max-w-3xl text-[0.9375rem] leading-[1.7] text-[#78756F]">
        Steloom помогает юридическим командам масштабировать свою экспертизу,
        сохраняя единый стандарт анализа, прозрачность выводов и контроль над
        каждым этапом работы с документами.
      </p>
    </MarketingEditorialShell>
  );
};

export default SolutionsPage;


