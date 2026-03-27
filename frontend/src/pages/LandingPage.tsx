// =============================================================
// src/pages/LandingPage.tsx
// Лендинг LegalMAS — тёмный стиль
//
// ✏️  ДЛЯ РЕДАКТИРОВАНИЯ ТЕКСТА — правьте только объект CONTENT
//     ниже (строки ~20–140). Разметку трогать не нужно.
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Shield,
  FileText,
  Link2,
  ClipboardCheck,
  AlertTriangle,
  FileSpreadsheet,
  Building2,
  Handshake,
  FileSearch,
  Lock,
  Users,
  CheckCircle2,
  ClipboardList,
  X,
} from "lucide-react";

// =============================================================
// ✏️  КОНТЕНТ — правьте этот объект для изменения текстов
// =============================================================
const CONTENT = {
  brand: {
    name: "LegalMAS",
    tagline: "Система интеллектуального анализа правовых документов",
    copyright: "© 2026 LegalMAS. Все права защищены.",
  },

  hero: {
    eyebrow: "Правовой анализ нового поколения",
    headlinePlain: "Юридический анализ",
    headlineAccent: "на новом уровне",
    subheadline:
      "Профессиональная платформа, которая берёт на себя рутинную проверку договоров и даёт юристу чёткую картину рисков — быстро, структурированно и с доказательной базой.",
    ctaPrimary: "Войти в систему",
    ctaSecondary: "Узнать больше",
  },

  // ✏️ Цифры-якоря под Hero — меняйте по необходимости
  stats: [
    { value: "500+",   label: "документов за один прогон" },
    { value: "4",      label: "уровня классификации L1–L4" },
    { value: "152-ФЗ", label: "соответствие требованиям" },
    { value: "Local",  label: "данные не покидают контур" },
  ],

  features: {
    sectionTitle: "Что делает система",
    sectionSubtitle:
      "Загрузите пакет документов, задайте параметры проверки — и получите готовый аналитический отчёт с перечнем нарушений, рисков и запросов к контрагенту.",
    items: [
      {
        icon: FileText,
        title: "Распознаёт тип документа",
        description:
          "Договор купли-продажи, NDA, трудовой договор, акт, приложение — и язык оригинала (русский, английский).",
      },
      {
        icon: Link2,
        title: "Выявляет связи между документами",
        description:
          "Основной договор → приложения → дополнительные соглашения → черновики — система строит полную карту семей документов.",
      },
      {
        icon: ClipboardCheck,
        title: "Проверяет по плейбуку",
        description:
          "Каждый документ проходит проверку по чек-листу, настроенному под тип сделки и юрисдикцию.",
      },
      {
        icon: AlertTriangle,
        title: "Присваивает уровень критичности",
        description:
          "Каждое нарушение получает метку: критический / высокий / средний. Сначала — самое важное.",
      },
      {
        icon: ClipboardList,
        title: "Формирует перечень запросов",
        description:
          "Пронумерованный список запросов к контрагенту (Приложение А к DD-отчёту) генерируется автоматически.",
      },
      {
        icon: FileSpreadsheet,
        title: "Экспортирует результаты",
        description:
          "Excel (DD Grid), Word-отчёт с резюме исполнительного уровня и сводная таблица — в несколько кликов.",
      },
    ],
  },

  scenarios: {
    sectionTitle: "Три ключевых сценария применения",
    items: [
      {
        icon: Building2,
        title: "Корпоративный комплаенс",
        description:
          "Загрузите весь пул договоров компании и проверьте его на соблюдение внутренних политик безопасности, принятых обязательств и требований законодательства (в том числе 152-ФЗ). Система сама укажет страницу и пункт договора, где обнаружена проблема.",
      },
      {
        icon: Handshake,
        title: "Сделки M&A и Due Diligence",
        description:
          "LegalMAS обрабатывает всю Data Room за один прогон: классифицирует документы, строит карту семей, прогоняет по DD-плейбуку и выдаёт структурированный отчёт с автоматически сформированным списком запросов к продавцу.",
      },
      {
        icon: FileSearch,
        title: "Анализ единичного договора",
        description:
          "Загрузите документ, выберите профиль проверки (стандартный, расширенный или максимальный) — и через минуты получите список пунктов, требующих внимания, с точными ссылками на текст.",
      },
    ],
  },

  security: {
    sectionTitle: "Контроль качества и безопасность",
    items: [
      {
        icon: CheckCircle2,
        title: "Верифицируемые выводы",
        text: "Каждое заключение сопровождается показателем достоверности и ссылкой на конкретный фрагмент документа — юрист всегда может проверить и скорректировать результат вручную.",
      },
      {
        icon: Shield,
        title: "Журнал аудита",
        text: "Все действия фиксируются в неизменяемом журнале аудита.",
      },
      {
        icon: Lock,
        title: "Соответствие 152-ФЗ",
        text: "По умолчанию система работает в режиме local-only — персональные данные не передаются во внешние облачные сервисы.",
      },
      {
        icon: Users,
        title: "Ролевая модель",
        text: "Администратор, редактор, наблюдатель — разграничение доступа на уровне каждого проекта для безопасной командной работы.",
      },
    ],
    roleCard: {
      title: "Ролевая модель доступа",
      roles: [
        {
          name: "Администратор",
          description: "Управление проектом и участниками",
          color: "border-red-500/30 bg-red-500/10 text-red-300",
        },
        {
          name: "Редактор",
          description: "Загрузка документов, запуск анализа, QC",
          color: "border-blue-500/30 bg-blue-500/10 text-blue-300",
        },
        {
          name: "Наблюдатель",
          description: "Просмотр отчётов и результатов",
          color: "border-slate-500/30 bg-slate-500/10 text-slate-300",
        },
      ],
    },
  },

  contact: {
    // ✏️ Укажите свою почту здесь
    email: "vladimir.gorelov.mail@gmail.com",
    linkLabel: "Связаться с нами",
    modalTitle: "Связаться с нами",
    modalSubtitle: "Напишите нам — мы ответим в течение рабочего дня.",
    emailLabel: "Ваш email",
    emailPlaceholder: "your@email.com",
    messageLabel: "Сообщение",
    messagePlaceholder: "Опишите ваш вопрос или задачу...",
    submitLabel: "Отправить",
    cancelLabel: "Отмена",
    note: "Нажимая «Отправить», вы откроете письмо в вашем почтовом клиенте.",
  },
};

// =============================================================
// Компонент — разметка и стили. Текст не трогать.
// =============================================================
const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const [contactOpen, setContactOpen] = useState(false);
  const [formEmail, setFormEmail] = useState("");
  const [formMessage, setFormMessage] = useState("");

  const goToLogin = () => navigate("/login");

  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = encodeURIComponent("Запрос через LegalMAS");
    const body = encodeURIComponent(`От: ${formEmail}\n\n${formMessage}`);
    window.location.href = `mailto:${CONTENT.contact.email}?subject=${subject}&body=${body}`;
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white antialiased">

      {/* ── Header ─────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 bg-slate-950/90 backdrop-blur-md border-b border-white/8 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center shadow-lg shadow-blue-600/30">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <p className="text-base font-bold text-white leading-none">
                  {CONTENT.brand.name}
                </p>
                <p className="text-[11px] text-slate-500 leading-tight mt-0.5">
                  {CONTENT.brand.tagline}
                </p>
              </div>
            </div>
            <button
              onClick={goToLogin}
              className="px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors shadow-lg shadow-blue-600/25"
            >
              {CONTENT.hero.ctaPrimary}
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────── */}
      <section className="relative py-24 lg:py-36 bg-slate-950 overflow-hidden">
        {/* Фоновое свечение */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[600px] bg-blue-600/15 rounded-full blur-[140px]" />
          <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-indigo-600/10 rounded-full blur-[100px]" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          {/* Eyebrow */}
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-white/5 border border-white/10 rounded-full text-xs text-slate-400 mb-8">
            <Shield className="w-3.5 h-3.5 text-blue-400" />
            {CONTENT.hero.eyebrow}
          </div>

          {/* Headline */}
          <h1 className="text-5xl lg:text-7xl font-bold text-white mb-6 leading-[1.1] tracking-tight">
            {CONTENT.hero.headlinePlain}{" "}
            <span className="bg-gradient-to-r from-blue-400 via-indigo-400 to-violet-400 bg-clip-text text-transparent">
              {CONTENT.hero.headlineAccent}
            </span>
          </h1>

          <p className="text-lg lg:text-xl text-slate-400 mb-10 max-w-2xl mx-auto leading-relaxed">
            {CONTENT.hero.subheadline}
          </p>
        </div>
      </section>

      {/* ── Stats ──────────────────────────────────────────── */}
      <section className="border-t border-white/5 bg-slate-950 py-14">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 text-center">
            {CONTENT.stats.map((stat) => (
              <div key={stat.label}>
                <p className="text-3xl lg:text-4xl font-bold text-white mb-1">
                  {stat.value}
                </p>
                <p className="text-sm text-slate-500">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ───────────────────────────────────────── */}
      <section id="features" className="py-24 bg-slate-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <SectionHeader
            title={CONTENT.features.sectionTitle}
            subtitle={CONTENT.features.sectionSubtitle}
          />
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 mt-14">
            {CONTENT.features.items.map((f, i) => (
              <div
                key={i}
                className="p-6 bg-slate-800/50 rounded-2xl border border-white/8 hover:border-blue-500/40 hover:bg-slate-800 transition-all group"
              >
                <div className="w-10 h-10 bg-blue-500/15 border border-blue-500/20 rounded-xl flex items-center justify-center mb-4 group-hover:bg-blue-500/25 transition-colors">
                  <f.icon className="w-5 h-5 text-blue-400" />
                </div>
                <h3 className="text-base font-semibold text-white mb-2">
                  {f.title}
                </h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  {f.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Scenarios ──────────────────────────────────────── */}
      <section className="py-24 bg-slate-950">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <SectionHeader title={CONTENT.scenarios.sectionTitle} />
          <div className="grid lg:grid-cols-3 gap-5 mt-14">
            {CONTENT.scenarios.items.map((s, i) => (
              <div
                key={i}
                className="relative bg-slate-900 rounded-2xl border border-white/8 p-8 hover:border-indigo-500/40 transition-all overflow-hidden group"
              >
                {/* Subtle glow on hover */}
                <div className="absolute inset-0 bg-gradient-to-br from-blue-600/5 to-indigo-600/5 opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl" />
                <div className="relative">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl flex items-center justify-center mb-6 shadow-lg shadow-blue-600/20">
                    <s.icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="text-lg font-semibold text-white mb-3">
                    {s.title}
                  </h3>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    {s.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Security ───────────────────────────────────────── */}
      <section className="py-24 bg-slate-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-16 items-start">
            {/* Left */}
            <div>
              <h2 className="text-2xl lg:text-3xl font-bold text-white mb-10">
                {CONTENT.security.sectionTitle}
              </h2>
              <ul className="space-y-6">
                {CONTENT.security.items.map((item, i) => (
                  <li key={i} className="flex items-start gap-4">
                    <div className="w-9 h-9 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5">
                      <item.icon className="w-4 h-4 text-emerald-400" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white mb-1">
                        {item.title}
                      </p>
                      <p className="text-sm text-slate-400 leading-relaxed">
                        {item.text}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {/* Right — Role card */}
            <div className="bg-slate-800/60 border border-white/8 rounded-2xl p-8">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-6">
                {CONTENT.security.roleCard.title}
              </p>
              <div className="space-y-3">
                {CONTENT.security.roleCard.roles.map((r) => (
                  <div
                    key={r.name}
                    className={`flex items-center justify-between p-4 rounded-xl border ${r.color}`}
                  >
                    <span className="text-sm font-semibold">{r.name}</span>
                    <span className="text-xs opacity-70">{r.description}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer className="bg-slate-950 border-t border-white/5 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 flex-wrap justify-center md:justify-start">
            <div className="w-7 h-7 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-md flex items-center justify-center">
              <Shield className="w-4 h-4 text-white" />
            </div>
            <span className="text-xs text-slate-600">
              {CONTENT.brand.copyright}
            </span>
            <span className="text-slate-700 text-xs select-none">·</span>
            <button
              onClick={() => setContactOpen(true)}
              className="text-xs text-blue-500 hover:text-blue-400 transition-colors underline underline-offset-2"
            >
              {CONTENT.contact.linkLabel}
            </button>
          </div>
        </div>
      </footer>

      {/* ── Contact Modal ──────────────────────────────────── */}
      {contactOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
          onClick={(e) => e.target === e.currentTarget && setContactOpen(false)}
        >
          <div className="bg-slate-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-md p-8 relative">
            <button
              onClick={() => setContactOpen(false)}
              className="absolute top-4 right-4 text-slate-500 hover:text-slate-300 transition-colors"
              aria-label="Закрыть"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="mb-6">
              <div className="w-10 h-10 bg-blue-500/15 border border-blue-500/20 rounded-xl flex items-center justify-center mb-4">
                <Shield className="w-5 h-5 text-blue-400" />
              </div>
              <h2 className="text-xl font-bold text-white">
                {CONTENT.contact.modalTitle}
              </h2>
              <p className="text-sm text-slate-400 mt-1">
                {CONTENT.contact.modalSubtitle}
              </p>
            </div>
            <form onSubmit={handleContactSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  {CONTENT.contact.emailLabel}
                </label>
                <input
                  type="email"
                  required
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                  placeholder={CONTENT.contact.emailPlaceholder}
                  className="w-full px-3 py-2.5 text-sm bg-slate-800 border border-white/10 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  {CONTENT.contact.messageLabel}
                </label>
                <textarea
                  required
                  value={formMessage}
                  onChange={(e) => setFormMessage(e.target.value)}
                  placeholder={CONTENT.contact.messagePlaceholder}
                  rows={4}
                  className="w-full px-3 py-2.5 text-sm bg-slate-800 border border-white/10 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                />
              </div>
              <p className="text-xs text-slate-500">{CONTENT.contact.note}</p>
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => setContactOpen(false)}
                  className="flex-1 px-4 py-2.5 text-sm font-medium text-slate-300 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors"
                >
                  {CONTENT.contact.cancelLabel}
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors"
                >
                  {CONTENT.contact.submitLabel}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Вспомогательный компонент заголовка секции ──────────────
interface SectionHeaderProps {
  title: string;
  subtitle?: string;
}

const SectionHeader: React.FC<SectionHeaderProps> = ({ title, subtitle }) => (
  <div className="text-center max-w-2xl mx-auto">
    <h2 className="text-2xl lg:text-3xl font-bold text-white mb-3">
      {title}
    </h2>
    {subtitle && (
      <p className="text-base text-slate-400 leading-relaxed">{subtitle}</p>
    )}
  </div>
);

export default LandingPage;
