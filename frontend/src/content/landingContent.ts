import {
  FileSearch,
  GitBranch,
  Lock,
  CheckCircle2,
  Building2,
  Handshake,
  Scale,
  SearchCheck,
  ScanSearch,
  Workflow,
  FileSpreadsheet,
  Layers3,
  ArrowUpRight,
} from "lucide-react";

export const landingContent = {
  brand: {
    name: "LegalMAS",
    tagline: "Legal Multi-Agent System for document analysis",
  },

  // Верхнее меню: ВСЕ пункты ведут на секции внутри лендинга.
  nav: [
    { label: "Возможности", href: "/#capabilities" },
    { label: "Сценарии", href: "/#use-cases" },
    { label: "Безопасность", href: "/#security" },
    { label: "Архитектура", href: "/#architecture" },
  ],

  hero: {
    eyebrow: "Enterprise legal AI infrastructure",
    title: "Юридический анализ документов",
    description:
      "LegalMAS обеспечивает преобразование массива документов в юридически выверенный и структурированный результат, который включает проверку в соответствии с заданной инструкцией (playbook) проверки, выводы с прямой ссылкой на источник в исходном документе, конфиденциальную обработку данных и управляемая обработка \ анализ документации — от загрузки до формирования отчёта. Вместо работы с неструктурированным набором файлов юридическая команда получает прозрачный инструмент для проверки: по каждому разделу инструкции (playboo) фиксируется обоснованный ответ, а выявленные риски - задокументированными. Такой подход формирует полноценную, обоснованную базу для принятия решений лицами, отвечающими за стратегическое управление и комплаенс.",
    primaryCta: "Запросить демо",
    secondaryCta: "Посмотреть сценарии",
    chips: [
      "Playbook-driven review",
      "Local-first LLM",
      "Traceable outputs",
      "PII-sanitized cloud mode",
    ],
    panelTitle:
      "Почему LegalMAS выглядит как enterprise product, а не как AI-обёртка",
    panelItems: [
      "Проверки строятся вокруг юридических playbooks, а не вокруг одного промпта.",
      "Каждый вывод привязан к источнику и пригоден для review.",
      "Local-first архитектура подходит для чувствительных документов.",
      "Облачные LLM могут подключаться только в контролируемом режиме.",
    ],
  },

  trustStrip: [
    "Built for DD, M&A and legal ops",
    "Source-linked outputs",
    "Privacy-first by design",
    "Hybrid retrieval + rule-based checks",
    "Audit-ready workflow",
  ],

  capabilities: {
    title: "Что делает LegalMAS",
    subtitle:
      "LegalMAS помогает юридическим командам не просто находить текст, а проходить документный массив через управляемый сценарий анализа.",
    featured: [
      {
        icon: FileSearch,
        title: "Playbook-driven analysis",
        description:
          "Платформа применяет юридические проверки по настраиваемым playbooks, чтобы команда получала единый, повторяемый и контролируемый подход к review.",
      },
      {
        icon: GitBranch,
        title: "Работа с пакетами документов и их связями",
        description:
          "LegalMAS анализирует не только отдельный документ, но и целый пакет сделки: дубликаты, версии, связи и контекст между файлами.",
      },
    ],
    support: [
      {
        icon: Lock,
        title: "Privacy-first architecture",
        description:
          "Система ориентирована на локальную обработку данных и controlled cloud usage для чувствительных сценариев.",
      },
      {
        icon: CheckCircle2,
        title: "Explainable outputs",
        description:
          "Каждый вывод связан с конкретным фрагментом текста и может быть проверен юристом.",
      },
      {
        icon: FileSpreadsheet,
        title: "Structured reporting",
        description:
          "Результаты готовы к экспорту в рабочие таблицы и дальнейшему юридическому отчёту.",
      },
    ],
  },

  workflow: {
    title: "Как проходит document flow",
    subtitle:
      "На главной — только короткий preview. Полный технический пайплайн раскрывается на отдельной архитектурной странице.",
    steps: [
      {
        icon: ScanSearch,
        title: "Ingest",
        text: "Загрузка PDF, DOCX, XLSX и сканов в единый поток обработки.",
      },
      {
        icon: Workflow,
        title: "Normalize",
        text: "OCR, language detection, structure parsing и semantic chunking.",
      },
      {
        icon: Layers3,
        title: "Evaluate",
        text: "Hybrid retrieval, playbook checks, LLM + rules logic и risk detection.",
      },
      {
        icon: ArrowUpRight,
        title: "Report",
        text: "Структурированный результат с source links, статусами и export-ready форматом.",
      },
    ],
  },

  whyChoose: {
    title: "Почему legal teams выбирают LegalMAS",
    items: [
      {
        title: "Не summary, а рабочий юридический результат",
        text: "Система ориентирована на review, due diligence и контроль риска, а не просто на общие AI-ответы.",
      },
      {
        title: "Контроль остаётся у юриста",
        text: "AI снимает рутинную обработку, но финальная экспертиза и проверка остаются у команды.",
      },
      {
        title: "Подходит для чувствительных контуров",
        text: "Local-first режим, PII-санация и auditability делают продукт релевантным enterprise-сценариям.",
      },
    ],
  },

  security: {
    title: "Безопасность встроена в архитектуру",
    description:
      "Для юридического AI trust layer — это не отдельная страница, а часть самого продукта: local-first подход, PII gateway, role-based access и прозрачный audit trail.",
    badges: [
      "Local-first processing",
      "PII sanitization gateway",
      "Role-based access",
      "Audit trail",
    ],
    cards: [
      {
        title: "Local-first по умолчанию",
        text: "Документы не должны покидать контур без явного решения администратора.",
      },
      {
        title: "Controlled cloud mode",
        text: "Если внешние LLM подключаются, это делается в управляемом режиме с предварительной санацией данных.",
      },
      {
        title: "Source-linked + audit-ready",
        text: "Результаты подходят для review, внутреннего контроля и объяснимого анализа.",
      },
    ],
    linkLabel: "Подробнее о privacy-first архитектуре",
  },

  useCases: {
    title: "Кому и для чего подходит LegalMAS",
    items: [
      {
        icon: Handshake,
        title: "M&A и Due Diligence",
        description:
          "Проверка Data Room, playbook-анализ, выявление рисков и подготовка структуры для DD-отчёта.",
      },
      {
        icon: Building2,
        title: "Корпоративные правовые отделы",
        description:
          "Анализ действующих договоров на отклонения от стандарта, обязательства и риск-паттерны.",
      },
      {
        icon: Scale,
        title: "Контрактный review",
        description:
          "Быстрое выделение отклонений, ключевых условий и зон, которые требуют внимания юриста.",
      },
      {
        icon: SearchCheck,
        title: "Аудит и расследования",
        description:
          "Поиск проблемных формулировок и повторяющихся паттернов по большому архиву документов.",
      },
    ],
  },

  architecturePreview: {
    title: "Это полноценный pipeline, а не single-prompt AI",
    description:
      "LegalMAS строится как многоступенчатая event-driven система: ingestion, OCR, структурирование, retrieval, checks execution, normalization и export.",
    bullets: [
      "OCR и text extraction",
      "Language detection",
      "PII sanitization",
      "Document structure parsing",
      "Hybrid retrieval + checks",
      "Async export pipeline",
    ],
    linkLabel: "Открыть архитектуру и пайплайн",
  },

  finalCta: {
    title: "Покажем LegalMAS на твоём document workflow",
    description:
      "На демо можно пройти путь от пакета документов и playbook-проверок до финального структурированного результата и export-ready output.",
    primary: "Запросить демо",
    secondary: "Изучить сценарии",
  },
} as const;

