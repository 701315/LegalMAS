// src/marketing/pages/SecurityPage.tsx
import React, { useState } from "react";
import { ArrowRight } from "lucide-react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { useContactModal } from "../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────────────────────
// Типы
// ─────────────────────────────────────────────────────────────────────────────

interface SecurityFeature {
  label: string;
  title: string;
  subtitle?: string;
  paragraphs: string[];
  bullets: string[];
}

interface ControlRow {
  area: string;
  measure: string;
  status: "foundation" | "partial" | "next";
}

interface ComplianceStandard {
  title: string;
  rows: ControlRow[];
}

interface ArchitectureCard {
  title: string;
  description: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Контент
// ─────────────────────────────────────────────────────────────────────────────

const FEATURES: SecurityFeature[] = [
  {
    label: "Обработка данных",
    title: "Документы остаются внутри вашей инфраструктуры",
    subtitle: "Local-First Processing",
    paragraphs: [
      "По умолчанию все этапы обработки документов — от извлечения текста до формирования результатов анализа — выполняются внутри контролируемого контура организации. Данные не передаются во внешние сервисы автоматически.",
      "Платформа может быть развернута в локальной инфраструктуре, частном облаке или ином доверенном контуре, соответствующем требованиям безопасности организации. Решение о том, где обрабатываются данные, принимает сама организация.",
    ],
    bullets: [
      "Обработка документов внутри корпоративного контура по умолчанию",
      "Организация определяет модель развертывания",
      "Данные не передаются во внешние сервисы без явного решения",
      "Единые принципы обработки независимо от варианта развертывания",
    ],
  },
  {
    label: "Защита данных",
    title: "Защита данных при использовании внешних моделей",
    subtitle: "PII Sanitization Gateway",
    paragraphs: [
      "Если для отдельных задач организация решает использовать внешние языковые модели, Steloom может автоматически обезличить документ перед передачей.",
      "PII Sanitization Gateway обнаруживает персональные данные, наименования компаний, реквизиты, банковскую информацию и другие чувствительные элементы и заменяет их нейтральными идентификаторами. При этом структура документа и контекст, необходимые для анализа, сохраняются, что позволяет модели выполнить обработку без доступа к исходным конфиденциальным данным.",
      "После обработки результаты автоматически сопоставляются с оригинальным документом внутри защищенного контура. Юрист получает привычный текст с реальными именами и реквизитами, а внешняя модель не работает с исходными данными в открытом виде.",
    ],
    bullets: [
      "Конфиденциальные данные обезличиваются до передачи за пределы контура",
      "Структура документа и контекст анализа сохраняются",
      "Восстановление исходных данных происходит только внутри инфраструктуры организации",
      "Подключение внешних моделей всегда определяется политикой организации",
    ],
  },
  {
    label: "Управление доступом",
    title: "Каждый пользователь видит только то, что ему разрешено",
    paragraphs: [
      "В юридической практике не все участники проекта должны иметь одинаковый доступ. Партнеру может быть доступен весь пакет сделки, младшему юристу — определенные документы, клиенту — итоговый отчет, а внешнему консультанту — ограниченный набор материалов.",
      "Steloom использует ролевую модель доступа, в которой права определяются функцией пользователя в проекте. Разграничение распространяется не только на документы, но и на результаты анализа, настройки проверки и административные функции.",
    ],
    bullets: [
      "Доступ определяется ролью пользователя в проекте",
      "Разграничение распространяется на документы, findings и настройки",
      "Чувствительная информация доступна только ограниченному кругу пользователей",
      "Модель доступа соответствует принципам, принятым в юридической практике",
    ],
  },
  {
    label: "Журнал аудита",
    title: "Полная история обработки документов",
    subtitle: "Audit Trail",
    paragraphs: [
      "Steloom фиксирует ключевые события обработки документов и действий пользователей внутри платформы: загрузку файлов, запуск анализа, применение правил проверки, изменения статуса findings, подтверждение или отклонение замечаний, обновления версий и экспорт результатов.",
      "Это позволяет восстановить последовательность обработки в любой момент, понять, кем и когда было выполнено действие, и подтвердить соблюдение внутренних процедур. Журнал аудита может использоваться для внутреннего контроля качества, совместной работы команды и проверок со стороны функций безопасности и compliance.",
    ],
    bullets: [
      "Фиксация ключевых событий обработки каждого документа",
      "Возможность восстановить историю действий по проекту",
      "Прозрачность процессов для внутреннего контроля и compliance",
      "Единая история изменений для всех участников проекта",
    ],
  },
  {
    label: "Развертывание",
    title: "Готов к работе в Enterprise-среде",
    paragraphs: [
      "Steloom поддерживает различные варианты развертывания — от локальной инфраструктуры до частного облака. Архитектура позволяет интегрировать платформу с корпоративными хранилищами, DMS, Data Room, системами управления доступом и внутренними сервисами организации.",
      "Платформа может внедряться поэтапно — начиная с отдельных сценариев анализа документов и постепенно расширяясь по мере роста потребностей организации.",
    ],
    bullets: [
      "Локальное развертывание или частное облако",
      "Интеграция с корпоративными системами и хранилищами",
      "Внедрение без перестройки существующих процессов",
      "Масштабирование вместе с потребностями организации",
    ],
  },
];

const ARCHITECTURE_CARDS: ArchitectureCard[] = [
  { title: "Local-first", description: "Документы обрабатываются внутри корпоративной инфраструктуры." },
  { title: "Tenant Isolation", description: "Изоляция данных организаций на уровне платформы." },
  { title: "RBAC", description: "Ролевое управление доступом к документам и результатам анализа." },
  { title: "Audit Logging", description: "Прослеживаемость ключевых действий пользователей и системы." },
  { title: "PII Sanitization", description: "Обезличивание чувствительных данных перед внешней обработкой." },
  { title: "Observability", description: "Logging, metrics и distributed tracing." },
  { title: "Controlled AI Access", description: "Подключение внешних моделей только по решению организации." },
  { title: "Request Traceability", description: "Сквозная прослеживаемость обработки запросов." },
  { title: "Enterprise Deployment", description: "Локальная инфраструктура, частное облако, корпоративная интеграция." },
];

const COMPLIANCE_STANDARDS: ComplianceStandard[] = [
  {
    title: "SOC 2 — соответствующие архитектурные меры",
    rows: [
      { area: "Аутентификация", measure: "Единая модель аутентификации пользователей", status: "foundation" },
      { area: "Управление доступом", measure: "Ролевая модель и tenant isolation", status: "foundation" },
      { area: "Разграничение на уровне проекта", measure: "Project / deal-level authorization", status: "foundation" },
      { area: "Журнал аудита", measure: "Фиксация ключевых событий обработки", status: "foundation" },
      { area: "Защита данных при передаче", measure: "TLS и безопасная передача данных", status: "foundation" },
      { area: "Session lifecycle", measure: "Контролируемый жизненный цикл сессий и revoke", status: "partial" },
      { area: "Мониторинг и обнаружение событий", measure: "Alerting, anomaly detection, review process", status: "partial" },
      { area: "Управление инцидентами", measure: "Формальный процесс реагирования", status: "next" },
      { area: "Управление поставщиками", measure: "Контроль внешних сервисов и провайдеров", status: "next" },
    ],
  },
  {
    title: "ISO/IEC 27001 — соответствующие архитектурные меры",
    rows: [
      { area: "Контроль доступа", measure: "Назначение и разграничение прав доступа", status: "foundation" },
      { area: "Журнал событий безопасности", measure: "Регистрация значимых действий", status: "foundation" },
      { area: "Защита данных при передаче", measure: "TLS, защита учетных данных и секретов", status: "foundation" },
      { area: "Мониторинг", measure: "Метрики, логи и корреляция событий", status: "partial" },
      { area: "Практики безопасной разработки", measure: "Контролируемые изменения и подтверждаемые процессы", status: "partial" },
      { area: "Управление уязвимостями", measure: "Выявление и устранение уязвимостей", status: "partial" },
      { area: "Резервное копирование и восстановление", measure: "Backup и проверяемое восстановление", status: "partial" },
      { area: "Управление инцидентами", measure: "Формальный процесс расследования", status: "next" },
      { area: "Управление поставщиками", measure: "Контроль внешних сервисов", status: "next" },
    ],
  },
  {
    title: "GDPR — соответствующие архитектурные меры",
    rows: [
      { area: "Privacy by Design", measure: "Защита данных встроена в архитектуру", status: "foundation" },
      { area: "PII Sanitization", measure: "Обезличивание чувствительных данных перед внешней обработкой", status: "foundation" },
      { area: "Контроль доступа к данным", measure: "Разграничение доступа и tenant isolation", status: "foundation" },
      { area: "Минимизация данных", measure: "Ограничение персональных данных в логах и телеметрии", status: "partial" },
      { area: "Политика хранения и удаления", measure: "Retention и deletion lifecycle", status: "partial" },
      { area: "Реестр операций обработки", measure: "Документирование процессов обработки данных", status: "next" },
    ],
  },
  {
    title: "152-ФЗ / ФСТЭК — соответствующие архитектурные меры",
    rows: [
      { area: "Идентификация и аутентификация", measure: "Единая модель аутентификации", status: "foundation" },
      { area: "Разграничение доступа", measure: "Ролевая модель, tenant isolation, ограничение привилегий", status: "foundation" },
      { area: "Регистрация событий безопасности", measure: "Audit trail значимых действий", status: "partial" },
      { area: "Контроль изменений и целостности", measure: "Контролируемые изменения и прослеживаемость", status: "partial" },
      { area: "Мониторинг и реагирование", measure: "Alerting, runbooks, восстановление после инцидентов", status: "next" },
    ],
  },
];

const SECURITY_PACKAGE_ITEMS = [
  "Security Architecture Overview",
  "Data Flow & Processing Architecture",
  "Authentication & Authorization Model",
  "Audit Logging Overview",
  "Deployment Architecture",
  "Security Controls Matrix",
  "Infrastructure Requirements",
  "Enterprise Security Briefing",
];

const SECURITY_REVIEW_TOPICS = [
  "Архитектуру развертывания",
  "Потоки данных и границы обработки",
  "Требования к инфраструктуре",
  "Модель аутентификации и управления доступом",
  "Возможности журналирования и аудита",
  "Архитектуру интеграции с корпоративными системами",
  "Дальнейшее развитие механизмов безопасности",
];

// ─────────────────────────────────────────────────────────────────────────────
// Subcomponents
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<ControlRow["status"], string> = {
  foundation: "Основа реализована",
  partial: "Частично реализовано",
  next: "Следующий этап",
};

const STATUS_COLORS: Record<ControlRow["status"], string> = {
  foundation: "bg-emerald-50 text-emerald-700 border-emerald-200",
  partial: "bg-amber-50 text-amber-700 border-amber-200",
  next: "bg-slate-50 text-slate-500 border-slate-200",
};

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="mt-6 space-y-3">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-4 text-[#78756F]">
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

function FeatureBlock({
  feature,
  index,
}: {
  feature: SecurityFeature;
  index: number;
}) {
  const isEven = index % 2 === 0;

  const textBlock = (
    <div className={`flex flex-col justify-center lg:col-span-7 ${isEven ? "" : "lg:order-2"}`}>
      <div className="eyebrow">{feature.label}</div>
      <h2 className="mt-4 font-serif text-[1.75rem] leading-tight tracking-[-0.03em] text-[#1A1917] lg:text-[2rem]">
        {feature.title}
      </h2>
      {feature.subtitle && (
        <h3 className="mt-3 text-lg font-semibold text-[#1A1917]">{feature.subtitle}</h3>
      )}
      <div className="mt-5 space-y-4">
        {feature.paragraphs.map((p, i) => (
          <p key={i} className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
            {p}
          </p>
        ))}
      </div>
    </div>
  );

  const bulletBlock = (
    <div className={`flex flex-col justify-center rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-6 lg:col-span-5 lg:p-8 ${isEven ? "" : "lg:order-1"}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#78756F]">
        Что это означает
      </p>
      <BulletList items={feature.bullets} />
    </div>
  );

  return (
    <div className="grid items-center gap-6 lg:grid-cols-12 lg:gap-10">
      {isEven ? (
        <>
          {textBlock}
          {bulletBlock}
        </>
      ) : (
        <>
          {bulletBlock}
          {textBlock}
        </>
      )}
    </div>
  );
}

function ComplianceAccordion({ standard }: { standard: ComplianceStandard }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-[#E8E4DD] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-4 py-5 text-left transition-colors hover:bg-[#FAF8F5]"
        aria-expanded={open}
      >
        <span className="text-[0.9375rem] font-medium leading-relaxed text-[#1A1917]">
          {standard.title}
        </span>
        <span
          className="mt-1 shrink-0 text-[#A8A29E] transition-transform duration-300"
          style={{ transform: open ? "rotate(45deg)" : "rotate(0deg)" }}
          aria-hidden="true"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
      </button>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? 1200 : 0, opacity: open ? 1 : 0 }}
      >
        <div className="overflow-x-auto pb-6 pr-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#E8E4DD] text-left text-[11px] font-semibold uppercase tracking-[0.18em] text-[#A8A29E]">
                <th className="pb-3 pr-4">Область требований</th>
                <th className="pb-3 pr-4">Архитектурная мера</th>
                <th className="pb-3">Статус</th>
              </tr>
            </thead>
            <tbody>
              {standard.rows.map((row) => (
                <tr key={row.area} className="border-b border-[#E8E4DD] last:border-0">
                  <td className="py-3.5 pr-4 font-medium text-[#1A1917]">{row.area}</td>
                  <td className="py-3.5 pr-4 text-[#78756F]">{row.measure}</td>
                  <td className="py-3.5">
                    <span className={`inline-block whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium ${STATUS_COLORS[row.status]}`}>
                      {STATUS_LABELS[row.status]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

const SecurityPage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const [complianceOpen, setComplianceOpen] = useState(false);

  return (
    <MarketingEditorialShell
      title="Безопасность, заложенная в архитектуру"
      description="Юридические документы содержат коммерческую тайну, персональные данные и условия сделок. Их защита не может зависеть от отдельных настроек или внешних политик."
    >
      {/* ── Hero sub-description + CTA ──────────────────────────────────── */}
      <div className="mb-16 rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-7 lg:mb-20 lg:p-9">
        <p className="max-w-3xl text-[0.9375rem] leading-[1.7] text-[#78756F]">
          В Steloom решения о том, где обрабатываются документы, какие данные
          могут покидать корпоративный контур, кто получает к ним доступ и как
          фиксируются действия пользователей, определяются на уровне архитектуры
          платформы. Организация сохраняет контроль над своими данными на каждом
          этапе работы.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <button type="button" onClick={openContactModal} className="cta-primary">
            Запросить демонстрацию
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={openContactModal} className="cta-secondary">
            Связаться с командой
          </button>
        </div>
      </div>

      {/* ── Блоки 2–6: Feature blocks ────────────────────────────────────── */}
      <div className="space-y-10">
        {FEATURES.map((feature, index) => (
          <FeatureBlock key={feature.title} feature={feature} index={index} />
        ))}
      </div>

      {/* ── Блок 7: Security Architecture & Compliance Readiness ─────────── */}
      <div className="mt-16 lg:mt-20">
        <div className="mb-8">
          <div className="eyebrow">Архитектура безопасности</div>
          <h2 className="mt-4 font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Security Architecture &amp; Compliance Readiness
          </h2>
          <p className="mt-5 max-w-3xl text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Steloom разрабатывается с учетом требований международных стандартов
            безопасности и практик enterprise-развертывания. Ниже представлены
            архитектурные механизмы безопасности, реализованные в платформе,
            а также их соотношение с распространенными областями проверки.
          </p>
        </div>

        {/* Disclaimer */}
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-6 py-5 text-[0.875rem] leading-7 text-amber-800">
          <strong>Важно:</strong> данная информация отражает текущее состояние
          ключевых архитектурных и технических мер и не является подтверждением
          прохождения сертификации, формального соответствия стандартам или
          заключением внешнего аудитора.
        </div>

        {/* Architecture cards */}
        <div className="mt-10">
          <h3 className="font-serif text-xl leading-tight tracking-[-0.02em] text-[#1A1917]">
            Архитектура безопасности Steloom
          </h3>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {ARCHITECTURE_CARDS.map((card) => (
              <div
                key={card.title}
                className="rounded-2xl border border-[#E8E4DD] bg-[#FAF8F5] p-5"
              >
                <div className="text-sm font-semibold text-[#1A1917]">{card.title}</div>
                <div className="mt-2 text-[0.875rem] leading-6 text-[#78756F]">
                  {card.description}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Compliance Readiness */}
        <div className="mt-12">
          <h3 className="font-serif text-xl leading-tight tracking-[-0.02em] text-[#1A1917]">
            Compliance Readiness
          </h3>
          <p className="mt-4 max-w-3xl text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Ниже показано, как архитектурные механизмы платформы соотносятся с
            областями, которые обычно оцениваются в рамках enterprise security
            review. Эта информация помогает понять архитектуру решения и не
            является заявлением о формальном соответствии конкретному стандарту.
          </p>

          {/* Toggle */}
          <button
            type="button"
            onClick={() => setComplianceOpen((v) => !v)}
            className="mt-6 flex items-center gap-2 text-[0.9375rem] font-medium text-[#1A1917] transition hover:text-[#78756F]"
          >
            <span
              className="shrink-0 text-[#A8A29E] transition-transform duration-300"
              style={{ transform: complianceOpen ? "rotate(45deg)" : "rotate(0deg)" }}
              aria-hidden="true"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </span>
            {complianceOpen
              ? "Скрыть: соответствие стандартам"
              : "Подробнее: соответствие стандартам"}
          </button>

          {/* Compliance accordions */}
          <div
            className="overflow-hidden transition-all duration-500"
            style={{
              maxHeight: complianceOpen ? 6000 : 0,
              opacity: complianceOpen ? 1 : 0,
            }}
          >
            <div className="mt-6 rounded-2xl border border-[#E8E4DD] bg-white px-6 lg:px-8">
              {COMPLIANCE_STANDARDS.map((standard) => (
                <ComplianceAccordion key={standard.title} standard={standard} />
              ))}
            </div>

            {/* Legend */}
            <div className="mt-6 space-y-2.5 text-[0.875rem] text-[#78756F]">
              <div className="flex items-start gap-3">
                <span className={`mt-0.5 inline-block whitespace-nowrap rounded-full border px-3 py-0.5 text-xs font-medium ${STATUS_COLORS.foundation}`}>
                  Основа реализована
                </span>
                <span>— архитектурный механизм реализован и используется в текущей версии платформы</span>
              </div>
              <div className="flex items-start gap-3">
                <span className={`mt-0.5 inline-block whitespace-nowrap rounded-full border px-3 py-0.5 text-xs font-medium ${STATUS_COLORS.partial}`}>
                  Частично реализовано
                </span>
                <span>— механизм существует, ведется работа по расширению покрытия</span>
              </div>
              <div className="flex items-start gap-3">
                <span className={`mt-0.5 inline-block whitespace-nowrap rounded-full border px-3 py-0.5 text-xs font-medium ${STATUS_COLORS.next}`}>
                  Следующий этап
                </span>
                <span>— область определена, реализация запланирована в рамках развития платформы</span>
              </div>
            </div>
          </div>
        </div>

        {/* Security Package */}
        <div className="mt-12">
          <h3 className="font-serif text-xl leading-tight tracking-[-0.02em] text-[#1A1917]">
            Security Package
          </h3>
          <p className="mt-4 max-w-3xl text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Для проведения security review мы можем предоставить дополнительную
            техническую документацию. Состав пакета адаптируется под процесс
            оценки и модель развертывания вашей организации.
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {SECURITY_PACKAGE_ITEMS.map((item) => (
              <div
                key={item}
                className="rounded-xl border border-[#E8E4DD] bg-[#FAF8F5] px-4 py-3 text-sm font-medium text-[#1A1917]"
              >
                {item}
              </div>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <button type="button" onClick={openContactModal} className="cta-primary">
              Запросить Security Overview
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button type="button" onClick={openContactModal} className="cta-secondary">
              Запросить Compliance Package
            </button>
          </div>
        </div>

        {/* Closing note */}
        <p className="mt-10 max-w-3xl text-[0.9375rem] leading-[1.7] text-[#A8A29E]">
          Безопасность Steloom развивается вместе с платформой. По мере
          появления новых сценариев использования и требований корпоративных
          клиентов архитектура последовательно дополняется новыми техническими
          и организационными механизмами.
        </p>
      </div>

      {/* ── Блок 8: Security Review ──────────────────────────────────────── */}
      <div className="mt-16 rounded-2xl border border-[#E8E4DD] bg-white p-7 lg:mt-20 lg:p-10">
        <div className="eyebrow">Security Review</div>
        <h2 className="mt-4 font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
          Поддержка технической оценки платформы
        </h2>
        <p className="mt-5 max-w-3xl text-[0.9375rem] leading-[1.7] text-[#78756F]">
          Если ваша организация проводит security review или архитектурную оценку
          решения, команда Steloom готова предоставить необходимую техническую
          информацию и принять участие в обсуждении архитектуры платформы.
        </p>
        <p className="mt-5 text-[0.9375rem] font-medium text-[#1A1917]">
          В рамках security review мы готовы обсудить:
        </p>
        <BulletList items={SECURITY_REVIEW_TOPICS} />
        <div className="mt-8 flex flex-wrap gap-3">
          <button type="button" onClick={openContactModal} className="cta-primary">
            Запросить Security Review
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={openContactModal} className="cta-secondary">
            Связаться с командой
          </button>
        </div>
      </div>

      {/* ── Блок 9: CTA ──────────────────────────────────────────────────── */}
      <div className="mt-16 rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-7 lg:mt-20 lg:p-10">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Убедитесь, как Steloom защищает ваши документы на&nbsp;практике
          </h2>
          <p className="mt-5 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Во время демонстрации мы покажем, как работают локальная обработка,
            защита конфиденциальных данных, управление доступом и журнал аудита
            на реальных юридических документах.
          </p>
          <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Если у вас есть собственные договоры или материалы сделки, их можно
            использовать в качестве примера. Это позволит оценить работу
            платформы в условиях, максимально приближенных к вашим внутренним
            требованиям безопасности.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button type="button" onClick={openContactModal} className="cta-primary">
              Запросить демонстрацию
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button type="button" onClick={openContactModal} className="cta-secondary">
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
        Безопасность — не отдельная функция платформы, а один из принципов ее
        архитектуры. Именно поэтому организации сохраняют контроль над своими
        документами, данными и процессами независимо от выбранной модели
        развертывания.
      </p>
    </MarketingEditorialShell>
  );
};

export default SecurityPage;


