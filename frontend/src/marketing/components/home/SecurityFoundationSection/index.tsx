import React from "react";
import { Link } from "react-router-dom";
import { 
  ArrowRight, 
  ShieldCheck, 
  Lock, 
  Users, 
  History, 
  Activity, 
  Settings2 
} from "lucide-react";
import { landingContent } from "../../../content/landingContent";

const SECURITY_TEASERS = [
  {
    icon: <ShieldCheck strokeWidth={1.2} className="h-7 w-7" />,
    title: "Local-First",
    desc: "Обработка данных внутри вашего контура"
  },
  {
    icon: <Lock strokeWidth={1.2} className="h-7 w-7" />,
    title: "PII Gateway",
    desc: "Автоматическое обезличивание перед LLM"
  },
  {
    icon: <Users strokeWidth={1.2} className="h-7 w-7" />,
    title: "RBAC",
    desc: "Разграничение прав на уровне проекта"
  },
  {
    icon: <History strokeWidth={1.2} className="h-7 w-7" />,
    title: "Audit Trail",
    desc: "Полная фиксация всех действий в логе"
  },
  {
    icon: <Activity strokeWidth={1.2} className="h-7 w-7" />,
    title: "Observability",
    desc: "Прозрачный мониторинг здоровья системы"
  },
  {
    icon: <Settings2 strokeWidth={1.2} className="h-7 w-7" />,
    title: "AI Governance",
    desc: "Организация сама определяет доступ к LLM моделям"
  }
];

const SecurityFoundationSection: React.FC = () => {
  const content = landingContent.security;

  return (
    <section
      id="security"
      className="relative flex min-h-screen items-center bg-[#FAF8F5] py-20 lg:py-28 border-y border-[#E8E4DD] scroll-mt-0"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-20">
          
          {/* ── Левая колонка: 6 тезисов (7 колонок — стала чуть уже) ── */}
          <div className="lg:col-span-7">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-12 lg:gap-y-16">
              {SECURITY_TEASERS.map((item, i) => (
                <div key={i} className="flex flex-col group">
                  <div className="mb-5 text-[#C86B52] transition-transform duration-500 group-hover:-translate-y-1">
                    {item.icon}
                  </div>
                  <h3 className="text-[1.125rem] font-medium text-[#1A1917] tracking-tight mb-2">
                    {item.title}
                  </h3>
                  <p className="text-[0.9375rem] leading-relaxed text-[#78756F] max-w-[280px]">
                    {item.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* ── Правая колонка: Текст (5 колонок — стала шире) ── */}
          <div className="flex flex-col justify-center lg:col-span-5 lg:sticky lg:top-32">
            <span className="eyebrow">{content.eyebrow}</span>

            <h2 className="section-title !mt-2 text-[#1A1917]">
              {content.title}
            </h2>

            <div className="mt-8 flex flex-col gap-6">
              <p className="text-[1.0625rem] leading-[1.7] text-[#78756F]">
                Безопасность Steloom строится на принципе нулевого доверия и полного контроля над данными внутри вашей организации.
              </p>
              <p className="text-[1.0625rem] leading-[1.7] text-[#78756F]">
                Каждый узел системы спроектирован так, чтобы исключить утечку конфиденциальной информации при работе с искусственным интеллектом. Платформа работает в вашем контуре, гарантируя неприкосновенность юридической тайны.
              </p>
            </div>

            <Link to="/security" className="cta-link mt-12">
              Подробнее об архитектуре безопасности
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

        </div>
      </div>
    </section>
  );
};

export default SecurityFoundationSection;


