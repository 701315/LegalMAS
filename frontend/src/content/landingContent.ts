// frontend/src/content/landingContent.ts

import {
  FileSearch,
  GitBranch,
  Lock,
  CheckCircle2,
  Building2,
  Handshake,
  Scale,
  ScanSearch,
  Workflow,
  FileSpreadsheet,
  Layers3,
  ArrowUpRight,
} from "lucide-react";

import localFirstImage from "../components/marketing/photo/Local-first.jpg";
import controlledCloudImage from "../components/marketing/photo/Controlled cloud.jpg";
import sourceLinkedImage from "../components/marketing/photo/Source-linked.jpg";

export const landingContent = {
  brand: {
    name: "Steloom",
    tagline: "The intelligence layer for legal work",
  },

  nav: [
    { label: "Возможности", href: "/capabilities" },
    { label: "Сценарии",    href: "/solutions" },
    { label: "Безопасность", href: "/security" },
    { label: "Архитектура", href: "/tech" },
  ],

  // ─── HERO ────────────────────────────────────────────────────────────────────
  hero: {
    eyebrow: "Intelligence layer for legal work",
    title: "Превращайте документы\nв структурированное знание.",
    description:
      "Steloom превращает массивы юридических документов в связанную, проверяемую и пригодную для работы интеллектуальную систему. Команда тратит меньше времени на ручное чтение, поиск и сверку — больше на выводы и решения.",
    primaryCta: "Запросить демо",
    secondaryCta: "Посмотреть сценарии",
    chips: [
      "Playbook-driven review",
      "Source-linked outputs",
      "Local-first LLM",
      "Audit-ready workflow",
    ],
    panelTitle: "Это не document viewer, не репозиторий и не чат",
    panelItems: [
      "Новый инфраструктурный слой для legal work — с архитектурой, а не с промптами.",
      "Проверки строятся вокруг вашего playbook, а не вокруг одного запроса.",
      "Каждый вывод привязан к источнику и пригоден для review и аудита.",
      "Local-first режим подходит для самых чувствительных документов.",
    ],
  },

  // ─── TRUST STRIP ─────────────────────────────────────────────────────────────
  trustStrip: [
    "Built for DD & M&A",
    "Source-linked outputs",
    "Privacy-first by design",
    "Hybrid retrieval + rule-based checks",
    "Audit-ready workflow",
    "Playbook-driven review",
    "Enterprise security",
  ],

  // ─── CONCEPT TAGS ────────────────────────────────────────────────────────────
  conceptTags: {
    eyebrow: "Что охватывает платформа",
    title: "Работа с документами,\nвыстроенная как система.",
    description:
      "Due diligence, clause extraction, risk mapping, obligation tracking, source-linked outputs, structure analysis — Steloom собирает разрозненные задачи в единый и управляемый процесс.",
    row1: [
      "Due Diligence",
      "Clause Extraction",
      "Risk Mapping",
      "M&A",
      "Data Room Analysis",
      "Playbook Review",
      "Obligation Tracking",
      "Deal Structuring",
    ],
    row2: [
      "Knowledge Graph",
      "Document Intelligence",
      "Structure Analysis",
      "Contract Review",
      "Audit Trail",
      "Source-linked Outputs",
      "Legal Ops",
      "Cross-reference",
    ],
  },

  // ─── AUDIENCE ────────────────────────────────────────────────────────────────
  audience: {
    eyebrow: "Для кого",
    title: "Одна платформа для \nключевых контуров legal work.",
    description:
      "Steloom релевантен нескольким ключевым ролям в юрфункции — не одному узкому пользователю.",
    roles: [
      {
        icon: Handshake,
        title: "M&A-команды",
        headline: "Скорость и контроль в data room.",
        body: "Структурированный review против playbook, автоматическое извлечение положений и рисков, прозрачный путь от документа к выводу. Сделка движется быстрее — без потери качества.",
        tags: ["Due Diligence", "Data Room", "Risk Extraction", "Playbook Review"],
      },
      {
        icon: Building2,
        title: "Legal Ops",
        headline: "Повторяемость, прозрачность и масштабирование.",
        body: "Стандартизированный процесс review, который не зависит от конкретного юриста. Steloom фиксирует методологию команды в playbook и воспроизводит её на каждом новом документном массиве.",
        tags: ["Process Standardization", "Audit Trail", "Workflow Automation"],
      },
      {
        icon: Scale,
        title: "General Counsel",
        headline: "Управляемый риск и доказуемость выводов.",
        body: "Каждый вывод привязан к источнику. Решения принимаются на основе проверяемых данных, а не пересказа. Steloom даёт ясность для управленческих решений и снижает цену пропущенного риска.",
        tags: ["Risk Management", "Decision Support", "Explainable Outputs"],
      },
    ],
  },

  // ─── STATS ───────────────────────────────────────────────────────────────────
  stats: {
    eyebrow: "Измеримый результат",
    title: "Эффект, который виден\nв сроках, часах и цене ошибки.",
    description:
      "Ускорение review, сокращение ручной аналитики и снижение стоимости пропущенного риска — как измеримый результат, а не абстрактное обещание технологии.",
    items: [
      {
        value: 10,
        suffix: "×",
        label: "Faster due diligence",
        sub: "vs. manual document review",
      },
      {
        value: 40,
        suffix: "h",
        label: "Saved per transaction",
        sub: "average across M&A workflows",
      },
      {
        value: 2,
        suffix: "M",
        prefix: "$",
        label: "Cost per missed clause",
        sub: "industry benchmark, top-tier deals",
      },
    ],
    quote:
      "Это не оценки. Это результаты, которые фиксируют юридические команды, заменившие ручной review структурированной аналитикой.",
  },

  // ─── CAPABILITIES ────────────────────────────────────────────────────────────
  capabilities: {
    eyebrow: "Возможности",
    title: "Ключевые операции поверх\nдокумента — в одной логике.",
    description:
      "Извлечение положений, навигация по рискам, привязка вывода к источнику, review по playbook, структурирование обязательств и формирование проверяемого результата — работают как единая система.",
    featured: [
      {
        icon: FileSearch,
        title: "Playbook-driven analysis",
        description:
          "Платформа применяет юридические проверки по настраиваемым playbooks — команда получает единый, повторяемый и контролируемый подход к review. Шаблон — только отправная точка, ядро — ваша логика.",
      },
      {
        icon: GitBranch,
        title: "Работа с пакетами и связями документов",
        description:
          "Steloom анализирует не отдельный документ, а целый пакет сделки: дубликаты, версии, перекрёстные ссылки и контекст между файлами. Ничто не теряется на странице 47.",
      },
    ],
    support: [
      {
        icon: Lock,
        title: "Privacy-first architecture",
        description:
          "Local-first обработка и PII-gateway перед внешними моделями. Документы не покидают контур без явного решения администратора.",
      },
      {
        icon: CheckCircle2,
        title: "Source-linked outputs",
        description:
          "Каждый вывод связан с конкретным фрагментом текста — пунктом, страницей, документом. Проверяем в одно касание.",
      },
      {
        icon: FileSpreadsheet,
        title: "Structured reporting",
        description:
          "Результаты готовы к экспорту в рабочие таблицы, DD-отчёт и дальнейшую работу команды.",
      },
    ],
  },

  // ─── ARCHITECTURE PREVIEW ────────────────────────────────────────────────────
  architecturePreview: {
    eyebrow: "Архитектура",
    title: "За выводом стоит не магия\nмодели, а воспроизводимая система.",
    description:
      "В основе Steloom — структурные слои обработки, связи между сущностями и понятный путь от исходного документа к итоговому выводу. Это делает результат не только быстрым, но и объяснимым.",
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
    bullets: [
      "OCR и text extraction",
      "Language detection",
      "PII sanitization",
      "Document structure parsing",
      "Hybrid retrieval + checks",
      "Event-driven pipeline",
    ],
    linkLabel: "Открыть архитектуру и пайплайн",
  },

  // ─── USE CASES ───────────────────────────────────────────────────────────────
  useCases: {
    eyebrow: "Use cases",
    title: "Интеллектуальная обработка\nна каждом этапе сделки.",
    description:
      "От due diligence до drafting, review и pre-closing — Steloom встроен в реальный рабочий цикл команды.",
    tabs: [
      {
        id: "diligence",
        label: "Due Diligence",
        headline: "Извлеките каждое обязательство до первого красного флага.",
        body: "Steloom обрабатывает data room против вашего playbook — каждое положение, риск и перекрёстная ссылка структурированы и доступны за часы, а не недели. Ни одно условие не теряется на странице 47.",
        tags: ["Clause extraction", "Risk mapping", "Playbook review"],
        video: "/video/workflow-process.mp4",
      },
      {
        id: "drafting",
        label: "Drafting",
        headline: "Формируйте структуру договора на основе проверенных шаблонов.",
        body: "Интеллектуальная база сохраняет выверенные формулировки, связанные с источником. При разработке нового документа команда опирается на институциональную память, а не на личные заметки.",
        tags: ["Template intelligence", "Clause library", "Source-linked"],
        video: "/video/workflow-process.mp4",
      },
      {
        id: "review",
        label: "Review",
        headline: "Видите различия, риски и отступления — быстро и без пропусков.",
        body: "Steloom выделяет отклонения от стандартных позиций, автоматически связывает похожие положения в разных документах и показывает контекст каждого вывода через прямую ссылку на источник.",
        tags: ["Redline intelligence", "Cross-reference", "Deviation flags"],
        video: "/video/workflow-process.mp4",
      },
      {
        id: "closing",
        label: "Pre-Closing",
        headline: "Проверьте выполнение условий и закройте сделку уверенно.",
        body: "Трекер обязательств показывает статус каждого условия сделки в реальном времени. Команда видит что выполнено, что открыто и что требует эскалации — до подписания.",
        tags: ["Obligation tracking", "Closing checklist", "Audit trail"],
        video: "/video/workflow-process.mp4",
      },
    ],
  },

  // ─── SECURITY ────────────────────────────────────────────────────────────────
  security: {
    eyebrow: "Безопасность",
    title: "Контроль доступа, границы данных\nи доказуемость — по умолчанию.",
    description:
      "Роли и права доступа, контуры работы с чувствительными данными, source-linked outputs и audit trail делают Steloom понятным не только юристам, но и security / IT-функции. Продукт проходит enterprise security review.",
    badges: [
      "Local-first processing",
      "PII sanitization gateway",
      "Role-based access",
      "Audit trail",
    ],
    cards: [
      {
        title: "Local-first по умолчанию",
        text: "Документы не покидают контур без явного решения администратора.",
        image: localFirstImage,
      },
      {
        title: "Controlled cloud mode",
        text: "Внешние LLM подключаются в управляемом режиме с предварительной санацией данных.",
        image: controlledCloudImage,
      },
      {
        title: "Source-linked + audit-ready",
        text: "Результаты подходят для review, внутреннего контроля и объяснимого анализа.",
        image: sourceLinkedImage,
      },
    ],
    linkLabel: "Подробнее о privacy-first архитектуре",
  },

  // ─── TESTIMONIAL ─────────────────────────────────────────────────────────────
  testimonial: {
    eyebrow: "Команды, которые уже используют",
    title: "Команда должна доверять\nне только выводу, но и пути к нему.",
    quote:
      "Впервые за годы работы с data room у нас есть инструмент, который не просто ищет по тексту, а понимает структуру сделки. Steloom — это то, что мы искали под DD-процесс.",
    author: "Партнёр, M&A практика",
    company: "Крупная международная юрфирма",
    // Заглушка — заменить на реальные данные при появлении social proof
    placeholder: true,
  },

  // ─── FAQ ─────────────────────────────────────────────────────────────────────
  faq: {
    eyebrow: "FAQ",
    title: "Вопросы, которые задают\nдо того, как пойти в пилот.",
    description:
      "Мы не избегаем сложных вопросов. Здесь — честные ответы на то, что enterprise-команды спрашивают чаще всего.",
    contactLabel: "Задать свой вопрос →",
    contactHref: "mailto:hello@steloom.com",
    items: [
      {
        q: "Чем Steloom отличается от корпоративной базы знаний?",
        a: "База знаний хранит то, что вы сами туда положили. Steloom извлекает структурированное знание напрямую из документов — автоматически, с привязкой к источнику и в контексте вашего playbook. Это активный intelligence layer, а не пассивное хранилище.",
      },
      {
        q: "Можно ли работать с NDA-чувствительными документами без отправки во внешние модели?",
        a: "Да. Steloom поддерживает local-first режим обработки с PII-gateway перед обращением к внешним моделям. Для чувствительных сценариев документы не покидают контур вашей инфраструктуры.",
      },
      {
        q: "Что если модель сделает ошибку — как мы это увидим?",
        a: "Каждый вывод системы привязан к конкретному источнику — пункту, странице и документу. Вы всегда видите, на чём основан результат, и можете его проверить. Steloom проектировался как аудитируемая система, а не как black box.",
      },
      {
        q: "Как система работает с нестандартными структурами договоров?",
        a: "Steloom не опирается на жёсткие шаблоны структуры документа. Extraction работает на уровне смысла, а не форматирования. Нестандартные договоры, нетипичные нумерации и смешанные структуры обрабатываются корректно.",
      },
      {
        q: "Интеграция с нашей DMS / iManage / SharePoint — сколько это займёт?",
        a: "Базовая интеграция через API занимает от 3 до 7 рабочих дней. Более глубокая двусторонняя синхронизация зависит от вашей инфраструктуры. На этапе демо мы разбираем ваш конкретный стек и даём реалистичные сроки.",
      },
      {
        q: "Нужна ли отдельная IT-команда для внедрения?",
        a: "Нет. Стандартное внедрение проходит под руководством нашей команды без привлечения ваших IT-ресурсов. Типичный срок от контракта до первого рабочего review — 2 недели.",
      },
      {
        q: "Насколько система адаптируется к нашему playbook?",
        a: "Playbook-конфигурация — это ядро продукта, а не опция. Steloom работает с вашими приоритетами проверки, вашими критичными положениями и вашей логикой флагирования рисков. Шаблонный режим — только отправная точка для быстрого старта.",
      },
    ],
  },

  // ─── FINAL CTA ───────────────────────────────────────────────────────────────
  finalCta: {
    eyebrow: "The intelligence layer for legal work",
    title: "Превращайте документы\nв структурированное знание.",
    description:
      "Steloom даёт команде структурированное, проверяемое и пригодное к действию знание из любого набора документов — быстро, спокойно и без потери контроля.",
    primary: "Запросить демо",
    secondary: "Изучить сценарии",
    footnote: "Без обязательств. Внедрение за 2 недели.",
  },

  // ─── FOOTER ──────────────────────────────────────────────────────────────────
  footer: {
    tagline: "The intelligence layer for legal work.",
    description:
      "Intelligence layer for legal work. Playbook-driven review, source-linked outputs and controllable document workflows for M&A and corporate legal teams.",
    nav: {
      product: [
        { label: "Возможности", href: "/capabilities" },
        { label: "Сценарии", href: "/solutions" },
        { label: "Архитектура", href: "/tech" },
        { label: "О нас", href: "/about" },
      ],
      trust: [
        { label: "Безопасность", href: "/security" },
        { label: "Use cases", href: "/solutions" },
        { label: "Запросить демо", href: "/demo" },
      ],
    },
    legal: "© 2026 Steloom. All rights reserved.",
    built: "Built for sensitive legal workflows.",
  },
} as const;

