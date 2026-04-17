import {
  Upload,
  ScanText,
  Languages,
  Lock,
  Network,
  Scissors,
  Tags,
  GitBranch,
  Cpu,
  FileSpreadsheet,
  Layers3,
  Activity,
  Server,
} from "lucide-react";

export const techOverviewContent = {
  intro: {
    eyebrow: "Architecture",
    title: "Архитектура и технический пайплайн LegalMAS",
    description:
      "LegalMAS — это не единичный вызов LLM, а многоступенчатая event-driven система обработки документов: от импорта и OCR до retrieval, исполнения плейбуков, нормализации результата и асинхронного экспорта.",
  },

  pipeline: {
    title: "Пайплайн обработки документа",
    items: [
      {
        icon: Upload,
        stage: "Этап 1",
        title: "Импорт и нормализация формата",
        description:
          "Система принимает PDF, DOCX, XLSX и изображения. Office-файлы конвертируются через отдельный микросервис, после чего артефакт сохраняется и регистрируется в БД.",
      },
      {
        icon: ScanText,
        stage: "Этап 2",
        title: "OCR и извлечение текста",
        description:
          "Для текстовых PDF используется прямое извлечение текста, а для сканов — OCR-пайплайн. Это позволяет одинаково обрабатывать цифровые и сканированные юридические документы.",
      },
      {
        icon: Languages,
        stage: "Этап 3",
        title: "Определение языка и primary source",
        description:
          "Определяется первичный язык документа, а для двуязычных материалов строится унифицированное представление для последующего анализа.",
      },
      {
        icon: Lock,
        stage: "Этап 4",
        title: "PII-санация",
        description:
          "Перед обращением к внешним LLM чувствительные сущности проходят через слой PII-санации с возможностью управляемого восстановления в итоговом отчёте.",
      },
      {
        icon: Network,
        stage: "Этап 5",
        title: "Парсинг структуры документа",
        description:
          "LegalMAS строит структурную модель документа: разделы, подразделы, параграфы, вложенность и нумерацию для retrieval и объяснимого анализа.",
      },
      {
        icon: Scissors,
        stage: "Этап 6",
        title: "Семантическая нарезка на чанки",
        description:
          "Документ делится на чанки с учётом структуры, смысловой связности и токенного бюджета. Каждый чанк получает собственные метаданные.",
      },
      {
        icon: Tags,
        stage: "Этап 7",
        title: "Классификация типа документа",
        description:
          "Система определяет тип документа — NDA, SPA, SHA, кредитный договор и другие — чтобы применить нужные проверки и логику плейбука.",
      },
      {
        icon: GitBranch,
        stage: "Этап 8",
        title: "Детектирование связей между документами",
        description:
          "Внутри пакета сделки выявляются связи, версии, дубликаты и документные семейства, чтобы анализ шёл не по отдельным файлам, а по связанному корпусу.",
      },
      {
        icon: Cpu,
        stage: "Этап 9",
        title: "Исполнение плейбука и проверок",
        description:
          "Retrieval-движок находит релевантные фрагменты, engine исполняет проверки, LLM и rule-based логика формируют ответ, а затем результат нормализуется и сохраняется.",
      },
      {
        icon: FileSpreadsheet,
        stage: "Этап 10",
        title: "Генерация и экспорт отчёта",
        description:
          "После завершения проверок система формирует структурированный отчёт и экспортирует результаты в удобные рабочие форматы, включая Excel.",
      },
    ],
  },

  scale: {
    title: "Масштабируемость и архитектурные гарантии",
    items: [
      {
        icon: Layers3,
        title: "Event-driven pipeline",
        description:
          "Документ проходит по цепочке независимых задач. Каждый обработчик отвечает за свой этап и публикует следующую задачу, что упрощает горизонтальное масштабирование.",
      },
      {
        icon: Server,
        title: "Горизонтальное масштабирование воркеров",
        description:
          "Асинхронные воркеры и очередь задач позволяют независимо масштабировать этапы обработки документов и генерации результатов.",
      },
      {
        icon: Activity,
        title: "Наблюдаемость и readiness к autoscaling",
        description:
          "Метрики и monitoring-слой позволяют контролировать производительность и готовят систему к более зрелой cloud/Kubernetes эксплуатации.",
      },
    ],
  },

  stack: {
    title: "Технический стек",
    groups: [
      {
        name: "Backend",
        items: [
          "FastAPI + Uvicorn",
          "SQLAlchemy asyncio + asyncpg",
          "PostgreSQL",
          "Celery + Redis",
          "MinIO / S3-compatible storage",
        ],
      },
      {
        name: "AI / NLP / Retrieval",
        items: [
          "llama-cpp-python",
          "sentence-transformers + PyTorch",
          "rank-bm25",
          "natasha",
          "langdetect",
          "tiktoken",
        ],
      },
      {
        name: "Frontend",
        items: [
          "React",
          "TypeScript",
          "Vite",
          "TailwindCSS",
          "React Router",
          "TanStack Query",
          "Zustand",
        ],
      },
    ],
  },

  cta: {
    title: "Показать архитектуру на реальном document flow?",
    subtitle:
      "На демо можно пройти весь путь документа: от загрузки и классификации до playbook-проверок и экспорта результатов.",
    primary: "Запросить демо",
  },
} as const;

