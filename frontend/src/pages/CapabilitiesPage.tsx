import React from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Shield,
  FileSearch,
  FolderKanban,
  Network,
  Lock,
  Bot,
  FileCheck2,
  Database,
  Layers3,
} from "lucide-react";

const CapabilitiesPage: React.FC = () => {
  const capabilities = [
    {
      icon: <FolderKanban className="h-5 w-5 text-amber-200" />,
      title: "Управление Data Room и массивом документов",
      text:
        "LegalMAS собирает договоры, приложения, корпоративные документы и вложения в единый рабочий контур, где документы становятся не просто файлами, а частью структурированного анализа.",
    },
    {
      icon: <FileSearch className="h-5 w-5 text-amber-200" />,
      title: "Playbook-driven проверки",
      text:
        "Система проверяет документы не по одному универсальному промпту, а по заранее заданным юридическим playbooks: по типам рисков, условиям, обязательствам, ограничениям и отклонениям от политики сделки.",
    },
    {
      icon: <FileCheck2 className="h-5 w-5 text-amber-200" />,
      title: "Source-linked выводы",
      text:
        "Каждый вывод можно привязать к конкретному документу, фрагменту текста или источнику, чтобы результат был пригоден для review, обсуждения и повторной проверки.",
    },
    {
      icon: <Bot className="h-5 w-5 text-amber-200" />,
      title: "Контролируемое использование LLM",
      text:
        "LegalMAS позволяет подключать облачные или локальные модели в контролируемом режиме: с понятной зоной применения, ограничениями на чувствительные данные и сохранением управляемости процесса.",
    },
    {
      icon: <Lock className="h-5 w-5 text-amber-200" />,
      title: "Privacy-first обработка",
      text:
        "Архитектура платформы проектируется под чувствительные документы: локальный контур, минимизация передачи данных наружу, управляемые интеграции и предсказуемый маршрут обработки.",
    },
    {
      icon: <Network className="h-5 w-5 text-amber-200" />,
      title: "Сквозной document pipeline",
      text:
        "От загрузки документа до финального отчёта LegalMAS поддерживает единый pipeline: ingestion, OCR/извлечение, нормализация, проверка, агрегация выводов и формирование итогового результата.",
    },
    {
      icon: <Database className="h-5 w-5 text-amber-200" />,
      title: "Структурирование результатов",
      text:
        "Платформа собирает разрозненные находки в единый результат: по документам, темам, рискам, блокам playbook и приоритетам, чтобы команда не теряла контекст между файлами.",
    },
    {
      icon: <Layers3 className="h-5 w-5 text-amber-200" />,
      title: "Результат, пригодный для команды",
      text:
        "Выводы LegalMAS можно использовать внутри юридической команды, в работе с инвестиционным контуром, в due diligence и в обсуждении с бизнесом — без ручной пересборки анализа с нуля.",
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl supports-[backdrop-filter]:bg-slate-950/70">
        <div className="mx-auto flex h-16 w-full max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:h-[72px] lg:px-10 xl:px-12">
          <Link to="/" className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white text-slate-950 shadow-lg shadow-black/20">
              <Shield className="h-5 w-5" />
            </div>

            <div className="min-w-0">
              <div className="truncate text-sm font-semibold tracking-tight text-white">
                LegalMAS
              </div>
              <div className="hidden truncate text-[11px] text-slate-500 sm:block">
                Enterprise legal AI infrastructure
              </div>
            </div>
          </Link>

          <Link
            to="/"
            className="inline-flex items-center rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.08]"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            На главную
          </Link>
        </div>
      </header>

      <main className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(71,85,105,0.20),transparent_28%),radial-gradient(circle_at_78%_18%,rgba(245,158,11,0.10),transparent_30%),linear-gradient(180deg,#020617_0%,#020617_100%)]" />

        <div className="relative mx-auto w-full max-w-[1480px] px-4 pb-20 pt-16 sm:px-6 lg:px-10 lg:pt-24 xl:px-12">
          <div className="max-w-4xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-slate-400">
              <Shield className="h-3.5 w-3.5 text-amber-300" />
              Возможности LegalMAS
            </div>

            <h1 className="mt-6 max-w-5xl text-5xl font-semibold tracking-tight text-white sm:text-6xl lg:text-[5.1rem] lg:leading-[0.96]">
              Подробное описание
              <span className="block text-slate-400">
                возможностей платформы
              </span>
            </h1>

            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-slate-300 lg:text-xl">
              LegalMAS превращает большой массив договоров и документов в управляемый
              юридический процесс: от intake и анализа до source-linked выводов и
              итогового результата, пригодного для review и сделочной работы.
            </p>
          </div>

          <div className="mt-12 grid gap-4 lg:grid-cols-2">
            {capabilities.map((item) => (
              <div
                key={item.title}
                className="rounded-[28px] border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-amber-400/50 bg-slate-950/90 shadow-[0_10px_30px_rgba(0,0,0,0.45)]">
                  {item.icon}
                </div>

                <h2 className="mt-5 text-xl font-semibold tracking-tight text-white">
                  {item.title}
                </h2>

                <p className="mt-3 text-sm leading-relaxed text-slate-300 lg:text-[15px]">
                  {item.text}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-12 rounded-[32px] border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm lg:p-8">
            <h2 className="text-2xl font-semibold tracking-tight text-white">
              Как это работает на практике
            </h2>

            <div className="mt-6 grid gap-4 lg:grid-cols-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="text-xs uppercase tracking-[0.14em] text-amber-300">
                  01
                </div>
                <h3 className="mt-3 text-lg font-semibold text-white">
                  Загрузка
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Команда загружает документы, папки и материалы Data Room.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="text-xs uppercase tracking-[0.14em] text-amber-300">
                  02
                </div>
                <h3 className="mt-3 text-lg font-semibold text-white">
                  Обработка
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Платформа извлекает текст, структуру и метаданные документов.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="text-xs uppercase tracking-[0.14em] text-amber-300">
                  03
                </div>
                <h3 className="mt-3 text-lg font-semibold text-white">
                  Проверка
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  LegalMAS применяет playbooks и формирует source-linked выводы.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="text-xs uppercase tracking-[0.14em] text-amber-300">
                  04
                </div>
                <h3 className="mt-3 text-lg font-semibold text-white">
                  Результат
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Команда получает структурированный итог для review и отчётности.
                </p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default CapabilitiesPage;

