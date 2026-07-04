// src/marketing/components/home/SecurityFoundationSection/index.tsx
import React from "react";
import { Link } from "react-router-dom";
import { 
  ArrowUpRight, 
  ShieldCheck, 
  FileKey, 
  Server, 
  Eye, 
  Lock, 
  Network 
} from "lucide-react";
import { landingContent } from "../../../content/landingContent";

// Расширенная сетка из 6 пунктов безопасности
const CERTIFICATES = [
  {
    title: "ISO 27001 & SOC 2",
    desc: "Steloom полностью сертифицирован по стандарту ISO 27001 и соответствует требованиям SOC 2 Type II для управления данными.",
    icon: <ShieldCheck strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "GDPR & 152-ФЗ",
    desc: "Полное соответствие строжайшим стандартам конфиденциальности данных для безопасной работы с резидентами РФ и ЕС.",
    icon: <FileKey strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "Zero Data Training",
    desc: "AI-модели никогда не дообучаются на ваших данных. Вся обработка происходит в read-only режиме для моделей.",
    icon: <Lock strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "Изоляция контуров",
    desc: "Каждая сделка живёт в собственном физически изолированном контуре. Доступ строго контролируется RBAC-политиками.",
    icon: <Network strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "Гибридная архитектура LLM",
    desc: "Платформа настроена как на работу с локальными LLM в закрытом контуре, так и на облачные модели через строгий PII sanitization gateway.",
    icon: <Server strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "100% Аудит и прозрачность",
    desc: "Полный аудит исходных данных для работы LLM и сделанных ею выводов. Абсолютная прозрачность для пользователя без «чёрных ящиков».",
    icon: <Eye strokeWidth={1.5} className="h-6 w-6" />
  }
];

const SecurityFoundationSection: React.FC = () => {
  const content = landingContent.security;

  return (
    <section
      id="security"
      className="relative flex items-center bg-[#F8F7F4] py-24 sm:py-32 scroll-mt-0 border-y border-[#E5E2DA]"
      data-header-theme="light"
    >
      <div className="mx-auto w-full max-w-[1920px] px-6 lg:px-10 xl:px-12">
        <div className="grid items-start gap-16 lg:grid-cols-12 lg:gap-24">
          
          {/* ── Левая колонка: Сетка сертификатов (6 карточек) ── */}
          <div className="lg:col-span-7 xl:col-span-7">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-10">
              {CERTIFICATES.map((cert, i) => (
                <div 
                  key={i} 
                  className="flex flex-col border-t border-[#E5E2DA] pt-6"
                >
                  <h3 className="text-[1.125rem] font-medium text-stone-950 tracking-tight mb-3">
                    {cert.title}
                  </h3>
                  <p className="text-[0.95rem] leading-[1.6] text-stone-500 mb-8 flex-grow pr-4">
                    {cert.desc}
                  </p>
                  
                  {/* Иконка-бейджик */}
                  <div className="mt-auto inline-flex h-14 w-14 items-center justify-center rounded-full border border-[#E5E2DA] text-stone-400 bg-white/50">
                    {cert.icon}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Правая колонка: Текст ── */}
          <div className="flex flex-col justify-center lg:col-span-5 xl:col-span-5 lg:sticky lg:top-32">
            <span className="eyebrow">{content.eyebrow}</span>

            <h2 className="section-title !mt-2 whitespace-pre-line text-stone-950">
              {content.title}
            </h2>

            <div className="mt-8 flex flex-col gap-6">
              <p className="text-[1.05rem] leading-relaxed text-stone-600">
                {content.description}
              </p>
              
              <ul className="mt-2 space-y-4">
                {content.badges.map((badge, idx) => (
                  <li key={idx} className="flex items-start gap-4 text-stone-600">
                    <span className="mt-2.5 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[#2F5A4A]" />
                    <span className="text-[1.05rem] leading-relaxed">{badge}</span>
                  </li>
                ))}
              </ul>
            </div>

            <Link
              to="/security"
              className="mt-12 inline-flex w-fit items-center gap-2 rounded-full border border-stone-300 bg-white px-6 py-3 text-sm font-medium text-stone-700 shadow-sm transition-all hover:border-stone-400 hover:text-stone-950 hover:shadow-md"
            >
              {content.linkLabel}
              <ArrowUpRight size={16} />
            </Link>
          </div>

        </div>
      </div>
    </section>
  );
};

export default SecurityFoundationSection;

