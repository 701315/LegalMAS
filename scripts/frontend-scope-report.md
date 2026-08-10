# Frontend scope audit

- Source root: `/srv/steloom-dev/frontend/src`
- Excluded: `src/marketing`, `__tests__`, `*.test.*`, `*.spec.*`, `*.d.ts`
- Scanned at: 2026-08-08T19:06:23.054Z
- Scanned files: 286

## Priority summary

- must_audit: **15**
- should_audit: **56**
- watchlist: **58**
- low: **157**

## Top review queue

| Score | Bucket | Area | File |
|---:|---|---|---|
| 134 | must_audit | pages | `pages/tabs/RealEstateTab.tsx` |
| 132 | must_audit | pages | `pages/tabs/CounterpartiesTab.tsx` |
| 102 | must_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1TabPage.tsx` |
| 95 | must_audit | pages | `pages/tabs/audit/ClassificationAuditView.tsx` |
| 94 | must_audit | pages | `pages/tabs/overview/AnalysisResultsWidget.tsx` |
| 91 | must_audit | pages | `pages/tabs/DocumentsTab.tsx` |
| 89 | must_audit | layout | `components/layout/AppShell.tsx` |
| 89 | must_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1List.tsx` |
| 88 | must_audit | pages | `pages/tabs/overview/ProjectDomainDetailsPanel.tsx` |
| 87 | must_audit | pages | `pages/tabs/audit/ClassificationInvestigationDrawer.tsx` |
| 86 | must_audit | pages | `pages/tenant-admin/tabs/MonitoringTab.tsx` |
| 84 | must_audit | pages | `pages/tabs/AuditTab.tsx` |
| 80 | must_audit | pages | `pages/tabs/OverviewTab.tsx` |
| 80 | must_audit | pages | `pages/tabs/ReportTab.tsx` |
| 80 | must_audit | pages | `pages/tenant-admin/tabs/LogsTab.tsx` |
| 79 | should_audit | pages | `pages/DealPage.tsx` |
| 78 | should_audit | components | `components/evidence/EvidencePanel.tsx` |
| 78 | should_audit | pages | `pages/tabs/RequestsTab.tsx` |
| 76 | should_audit | pages | `pages/tabs/overview/LaunchWideOverlay.tsx` |
| 76 | should_audit | pages | `pages/tenant-admin/sections/project-drilldown/ProjectOverviewSection.tsx` |
| 74 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1TypedGroups.tsx` |
| 74 | should_audit | pages | `pages/tabs/overview/ProjectDomainsOverviewPanel.tsx` |
| 73 | should_audit | routing | `App.tsx` |
| 73 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1Matrix.tsx` |
| 70 | should_audit | pages | `pages/tabs/overview/LaunchFormPanel.tsx` |
| 69 | should_audit | pages | `pages/AdminPlaybookLinesPage.tsx` |
| 67 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1Drawer.tsx` |
| 66 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1InstructionDrawer.tsx` |
| 65 | should_audit | pages | `pages/TenantAdminPage.tsx` |
| 64 | should_audit | global-styles | `index.css` |
| 64 | should_audit | pages | `pages/tabs/overview/PipelineStepCard.tsx` |
| 63 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1ViewModeToggle.tsx` |
| 63 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1ViewSettings.tsx` |
| 63 | should_audit | pages | `pages/tenant-admin/tabs/ProjectsTab.tsx` |
| 63 | should_audit | pages | `pages/tenant-admin/tabs/UsersTab.tsx` |
| 61 | should_audit | components | `components/documents/pipeline/StructureStageViewer.tsx` |
| 60 | should_audit | pages | `pages/tabs/GridTab.tsx` |
| 58 | should_audit | components | `components/documents/pipeline/ChunksStageViewer.tsx` |
| 58 | should_audit | components | `components/settings/ProjectMembersPanel.tsx` |
| 58 | should_audit | pages | `pages/instructions/DocTypeDetailPage.tsx` |
| 58 | should_audit | pages | `pages/instructions/GlobalInstructionDetailPage.tsx` |
| 58 | should_audit | pages | `pages/PlaybooksRegistryPage.tsx` |
| 58 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1ExportLayoutPicker.tsx` |
| 56 | should_audit | pages | `pages/tabs/SettingsTab.tsx` |
| 55 | should_audit | pages | `pages/tenant-instructions/TenantBaseDocTypeDetailPage.tsx` |
| 55 | should_audit | pages | `pages/tenant-instructions/TenantBaseGlobalCheckDetailPage.tsx` |
| 54 | should_audit | pages | `pages/tabs/dd-grid-v1/DDGridV1ExportButtons.tsx` |
| 54 | should_audit | pages | `pages/tenant-admin/sections/project-drilldown/ProjectLogsSection.tsx` |
| 53 | should_audit | pages | `pages/tabs/overview/PipelinePreviewPanel.tsx` |
| 53 | should_audit | pages | `pages/tenant-admin/components/LogsTable.tsx` |

## Detailed findings

### pages/tabs/RealEstateTab.tsx

- score: **134**
- bucket: **must_audit**
- area: **pages**
- lines: **1897**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 16, count: 14)
  - L841: `<div className="overflow-hidden rounded-2xl border border-[var(--border)]">`
  - L886: `<div className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">`
  - L915: `<div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">`
  - L1084: `<div className="flex h-full min-h-0 flex-col overflow-hidden">`
  - L1120: `<div className="overflow-hidden rounded-2xl border border-[var(--border)]">`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L823: `style={{ width: '${share}%' }}`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 14, count: 4)
  - L1100: `<div className="grid grid-cols-1 gap-3 md:grid-cols-3">`
  - L1447: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-4">`
  - L1504: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-3">`
  - L1731: `<div className="mb-4 shrink-0 grid grid-cols-2 gap-3 xl:grid-cols-4">`
- [LOCAL_X_SCROLL] Есть локальный horizontal scroll — вероятно data-heavy surface (weight: 10, count: 2)
  - L842: `<div className="overflow-x-auto">`
  - L1121: `<div className="overflow-x-auto">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 15, count: 3)
  - L843: `<table className="min-w-full text-left text-sm">`
  - L1122: `<table className="min-w-full text-left text-sm">`
  - L1218: `<table className="min-w-full text-left text-sm">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L915: `<div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 11, count: 7)
  - L1100: `<div className="grid grid-cols-1 gap-3 md:grid-cols-3">`
  - L1400: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">`
  - L1447: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-4">`
  - L1504: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-3">`
  - L1551: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 10, count: 24)
  - L614: `"flex min-h-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",`
  - L620: `<div className="min-w-0">`
  - L635: `<div className={["min-h-0 flex-1 px-5 py-4", bodyClassName].join(" ")}>`
  - L646: `<div className="flex h-full flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">`
  - L786: `<div className="min-w-0 flex-1">`

### pages/tabs/CounterpartiesTab.tsx

- score: **132**
- bucket: **must_audit**
- area: **pages**
- lines: **1702**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 16, count: 8)
  - L822: `<div className="overflow-hidden rounded-2xl border border-[var(--border)]">`
  - L867: `<div className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">`
  - L896: `<div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">`
  - L1038: `<div className="flex h-full min-h-0 flex-col overflow-hidden">`
  - L1074: `<div className="overflow-hidden rounded-2xl border border-[var(--border)]">`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L804: `style={{ width: '${share}%' }}`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 13, count: 3)
  - L1054: `<div className="grid grid-cols-1 gap-3 md:grid-cols-3">`
  - L1294: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-3">`
  - L1532: `<div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">`
- [LOCAL_X_SCROLL] Есть локальный horizontal scroll — вероятно data-heavy surface (weight: 10, count: 2)
  - L823: `<div className="overflow-x-auto">`
  - L1075: `<div className="overflow-x-auto">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 15, count: 3)
  - L824: `<table className="min-w-full text-left text-sm">`
  - L1076: `<table className="min-w-full text-left text-sm">`
  - L1153: `<table className="min-w-full text-left text-sm">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L896: `<div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 10, count: 5)
  - L1054: `<div className="grid grid-cols-1 gap-3 md:grid-cols-3">`
  - L1294: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-3">`
  - L1338: `<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">`
  - L1532: `<div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">`
  - L1581: `<div className="grid h-full min-h-0 grid-cols-1 xl:grid-cols-2">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 10, count: 22)
  - L595: `"flex min-h-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",`
  - L601: `<div className="min-w-0">`
  - L616: `<div className={["min-h-0 flex-1 px-5 py-4", bodyClassName].join(" ")}>`
  - L627: `<div className="flex h-full flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">`
  - L767: `<div className="min-w-0 flex-1">`

### pages/tabs/dd-grid-v1/DDGridV1TabPage.tsx

- score: **102**
- bucket: **must_audit**
- area: **pages**
- lines: **1060**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 13, count: 5)
  - L366: `className={'grid overflow-hidden transition-[grid-template-rows,opacity,margin] duration-300 ease-out ${`
  - L404: `className={'grid overflow-hidden transition-[grid-template-rows,opacity] duration-300 ease-out ${`
  - L728: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden">`
  - L877: `className={'grid overflow-hidden transition-[grid-template-rows,opacity,margin] duration-300 ease-out ${`
  - L1015: `<div className="min-h-0 flex-1 overflow-hidden px-5 py-5 relative">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L923: `<div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 50)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1TabPage.tsx`
  - L3: `// V1 экран DD Grid.`
  - L6: `// - Блок "DD Grid" убран, сводка перенесена в subtitle секции;`
  - L25: `import { useDealReviewDdGridV1 } from "../../../api/dealReview";`
  - L28: `import DDGridV1TypedGroups from "./DDGridV1TypedGroups";`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L312: `<div className="flex min-h-[280px] flex-col items-center justify-center text-center">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L923: `<div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 9, count: 10)
  - L372: `<div className="min-h-0">`
  - L410: `<div className="min-h-0">`
  - L728: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden">`
  - L737: `<section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
  - L741: `<div className="min-w-0">`

### pages/tabs/audit/ClassificationAuditView.tsx

- score: **95**
- bucket: **must_audit**
- area: **pages**
- lines: **480**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L195: `<section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L236: `<table className="w-full min-w-[1120px] border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L236: `<table className="w-full min-w-[1120px] border-collapse">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L190: `? "lg:grid-cols-[minmax(0,2fr)_minmax(360px,1fr)]"`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 7, count: 1)
  - L465: `{/* ── Side panel: explainability drawer ────────────────── */}`
- [TAB_NAV] Есть tabs/tablist — важно для mobile nav и keyboard behavior (weight: 9, count: 1)
  - L316: `aria-selected={isSelected}`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 6, count: 5)
  - L188: `"grid min-h-0 flex-1 gap-4",`
  - L195: `<section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
  - L223: `<div className="flex min-h-0 flex-1 items-center justify-center">`
  - L235: `<div className="min-h-0 flex-1 overflow-auto">`
  - L321: `<div className="min-w-0">`

### pages/tabs/overview/AnalysisResultsWidget.tsx

- score: **94**
- bucket: **must_audit**
- area: **pages**
- lines: **850**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L733: `<div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L736: `style={{ width: '${progressPercent}%' }}`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 48)
  - L10: `//      результата. Клик по заголовку → DD Grid list mode +`
  - L14: `//      Клик → DD Grid + checksScope=doc_type_only.`
  - L19: `//      Ведёт в DD Grid list mode + checksScope=all + showPass=true.`
  - L38: `import { useDealReviewDdGridV1 } from "../../../api/dealReview";`
  - L39: `import { useDDGridV1UIStore } from "../dd-grid-v1/ddGridV1.collapseStore";`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 10, count: 6)
  - L280: `for (const [checkId, drawer] of Object.entries(drawerByCheck)) {`
  - L282: `if (!drawer) continue;`
  - L284: `const status = drawer.review_status;`
  - L579: `for (const drawer of Object.values(drawerByCheck)) {`
  - L580: `if (!drawer) continue;`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 6, count: 5)
  - L390: `<span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-primary)]">`
  - L443: `<p className="min-w-0 flex-1 truncate text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">`
  - L507: `<span className="min-w-0 flex-1 truncate text-[11px] leading-4 text-[var(--text-primary)]">`
  - L710: `<div className="min-w-0 flex-1">`
  - L735: `className="h-full rounded-full bg-[var(--accent-primary)] transition-all duration-500"`

### pages/tabs/DocumentsTab.tsx

- score: **91**
- bucket: **must_audit**
- area: **pages**
- lines: **771**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 16, count: 8)
  - L285: `className={'ml-2 flex origin-left items-center gap-2 overflow-hidden transition-all duration-300 ease-out ${`
  - L479: `<section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
  - L556: `<div className="flex min-h-0 flex-1 overflow-hidden">`
  - L558: `<div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[var(--bg-card)]">`
  - L568: `<div className="flex min-h-0 flex-1 flex-col overflow-hidden">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L582: `<table className="w-full border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 8, count: 2)
  - L287: `? "max-w-[340px] translate-x-0 opacity-100"`
  - L723: `<div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-[3px] bg-[var(--accent-primary)]" />`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L474: `? "lg:grid-cols-[minmax(0,2fr)_minmax(360px,1fr)]"`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 10, count: 12)
  - L120: `<div className="min-w-0 flex-1">`
  - L467: `className="flex h-full min-h-0 flex-col"`
  - L470: `<div className="relative flex min-h-0 flex-1 flex-col text-[var(--text-primary)]">`
  - L472: `className={'grid min-h-0 flex-1 gap-4 ${`
  - L479: `<section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`

### components/layout/AppShell.tsx

- score: **89**
- bucket: **must_audit**
- area: **layout**
- lines: **791**

- [APP_LAYOUT] Core layout / AppShell слой (weight: 40, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 11, count: 3)
  - L620: `<div className="flex h-full min-h-0 w-full overflow-hidden bg-[var(--bg-base)] text-[var(--text-primary)]">`
  - L648: `<main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--bg-base)]">`
  - L676: `<div className="min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--bg-surface)]">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 9, count: 3)
  - L28: `const DESKTOP_NAV_WIDTH_EXPANDED_CLASS = "lg:w-[248px] lg:min-w-[248px]";`
  - L29: `const DESKTOP_NAV_WIDTH_COLLAPSED_CLASS = "lg:w-[80px] lg:min-w-[80px]";`
  - L30: `const MOBILE_DRAWER_WIDTH_CLASS = "w-[248px] max-w-[85vw]";`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 2)
  - L623: `"relative hidden h-full min-h-0 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg-card)] transition-[width] duration-200 lg:flex",`
  - L682: `<div className="fixed inset-0 z-40 lg:hidden">`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 10, count: 5)
  - L553: `// Автоматически закрываем mobile drawer при любом изменении URL`
  - L694: `role="dialog"`
  - L738: `role="dialog"`
  - L740: `aria-labelledby="logout-dialog-title"`
  - L749: `id="logout-dialog-title"`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 10, count: 12)
  - L247: `<div className="relative flex h-full min-h-0 flex-col bg-[var(--bg-card)]">`
  - L257: `className="h-10 min-h-0 w-10 rounded-full p-0 shadow-sm"`
  - L274: `<div className="min-w-0">`
  - L294: `<div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-3">`
  - L413: `<span className="min-w-0 flex-1">`

### pages/tabs/dd-grid-v1/DDGridV1List.tsx

- score: **89**
- bucket: **must_audit**
- area: **pages**
- lines: **1266**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 11, count: 3)
  - L1187: `className={'flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm transition-all duration-200 ${`
  - L1191: `<div className="min-h-0 flex-1 overflow-hidden">`
  - L1232: `<div className="flex h-full min-h-0 min-w-[320px] flex-[1_1_0%] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 43)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1List.tsx`
  - L3: `// V1-native plain list findings из DD Grid V1 модели.`
  - L6: `// - source of truth — DDGridV1DerivedModel (без legacy адаптера);`
  - L25: `import { AgGridReact } from "ag-grid-react";`
  - L35: `} from "ag-grid-community";`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L1232: `<div className="flex h-full min-h-0 min-w-[320px] flex-[1_1_0%] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 10, count: 26)
  - L7: `// - клик по любой ячейке (кроме checkbox) открывает V1 drawer;`
  - L52: `} from "./ddGridV1.drawer";`
  - L97: `/** Drawer content для этой пары (или null, если backend не прислал). */`
  - L211: `function buildLocationText(drawer: DDGridV1DrawerContentDTO | null): string {`
  - L212: `if (!drawer) return "";`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 7, count: 7)
  - L790: `<div className="flex h-full items-center">`
  - L917: `<div className="flex h-full items-center">`
  - L1184: `<div ref={rootRef} className="flex h-full min-h-0 gap-4">`
  - L1187: `className={'flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm transition-all duration-200 ${`
  - L1191: `<div className="min-h-0 flex-1 overflow-hidden">`

### pages/tabs/overview/ProjectDomainDetailsPanel.tsx

- score: **88**
- bucket: **must_audit**
- area: **pages**
- lines: **423**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 11, count: 3)
  - L268: `Тогда родительский overflow-hidden режет контент снизу,`
  - L362: `"flex h-full min-h-0 flex-col overflow-hidden",`
  - L397: `<div className="min-h-0 flex-1 overflow-hidden px-5 py-4">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L279: `<div className="hidden h-full min-h-0 grid-cols-4 grid-rows-[minmax(0,1fr)] gap-4 xl:grid">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 2)
  - L279: `<div className="hidden h-full min-h-0 grid-cols-4 grid-rows-[minmax(0,1fr)] gap-4 xl:grid">`
  - L306: `<div className="grid min-h-0 grid-cols-1 gap-4 xl:hidden lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 9, count: 11)
  - L64: `<div className="flex min-h-0 min-w-0 flex-col">`
  - L68: `<div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">`
  - L266: `grid row растёт до размера этого контента и превышает h-full.`
  - L279: `<div className="hidden h-full min-h-0 grid-cols-4 grid-rows-[minmax(0,1fr)] gap-4 xl:grid">`
  - L306: `<div className="grid min-h-0 grid-cols-1 gap-4 xl:hidden lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">`

### pages/tabs/audit/ClassificationInvestigationDrawer.tsx

- score: **87**
- bucket: **must_audit**
- area: **pages**
- lines: **485**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 10, count: 2)
  - L142: `<aside className="relative flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
  - L365: `<div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L373: `style={{ width: '${pct}%' }}`
- [LOCAL_X_SCROLL] Есть локальный horizontal scroll — вероятно data-heavy surface (weight: 12, count: 6)
  - L300: `<pre className="mt-2 overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2 text-[10px] leading-4 text-[var(--text-secondary)]">`
  - L430: `<pre className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2 text-[10px] leading-4 text-[var(--text-secondary)]">`
  - L441: `<pre className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2 text-[10px] leading-4 text-[var(--text-secondary)]">`
  - L458: `<pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[10px] leading-4 text-[var(--text-secondary)]">`
  - L464: `<pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[10px] leading-4 text-[var(--text-secondary)]">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L144: `<div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-[3px] bg-[var(--accent-primary)]" />`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 7, count: 6)
  - L86: `<div className="min-w-0 break-words text-xs text-[var(--text-secondary)]">`
  - L142: `<aside className="relative flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
  - L148: `<div className="flex min-w-0 items-center gap-2">`
  - L172: `<div className="min-h-0 flex-1 overflow-y-auto bg-[var(--bg-elevated-soft)]">`
  - L332: `<div className="flex min-w-0 items-center gap-1.5">`

### pages/tenant-admin/tabs/MonitoringTab.tsx

- score: **86**
- bucket: **must_audit**
- area: **pages**
- lines: **415**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L126: `<div className="grid grid-cols-2 gap-2 sm:grid-cols-4">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 14, count: 2)
  - L225: `<table className="w-full min-w-[680px] border-collapse">`
  - L367: `<table className="w-full min-w-[480px] border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 10, count: 4)
  - L91: `<div className="flex h-full min-h-[240px] items-center justify-center text-[var(--text-muted)]">`
  - L103: `<div className="flex h-full min-h-[240px] items-center justify-center p-5">`
  - L225: `<table className="w-full min-w-[680px] border-collapse">`
  - L367: `<table className="w-full min-w-[480px] border-collapse">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 2)
  - L126: `<div className="grid grid-cols-2 gap-2 sm:grid-cols-4">`
  - L283: `<div className="grid gap-4 xl:grid-cols-2">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 6, count: 5)
  - L90: `<div className="min-h-0 flex-1 overflow-auto">`
  - L91: `<div className="flex h-full min-h-[240px] items-center justify-center text-[var(--text-muted)]">`
  - L102: `<div className="min-h-0 flex-1 overflow-auto">`
  - L103: `<div className="flex h-full min-h-[240px] items-center justify-center p-5">`
  - L123: `<div className="min-h-0 flex-1 overflow-auto">`

### pages/tabs/AuditTab.tsx

- score: **84**
- bucket: **must_audit**
- area: **pages**
- lines: **471**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L249: `<div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-card)]">`
- [LOCAL_X_SCROLL] Есть локальный horizontal scroll — вероятно data-heavy surface (weight: 9, count: 1)
  - L251: `<div className="h-full overflow-y-auto overflow-x-auto">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L252: `<table className="w-full table-fixed border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 8, count: 2)
  - L130: `<div className="flex min-h-[320px] flex-col items-center justify-center text-center">`
  - L343: `<td className="max-w-[380px] px-3 py-2.5 text-[11px] text-[var(--text-secondary)]">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 9, count: 11)
  - L150: `<div className="flex h-full min-h-0 flex-col">`
  - L209: `className="flex-1 min-h-0"`
  - L210: `contentClassName="flex min-h-0 flex-1 flex-col"`
  - L211: `bodyClassName="flex h-full min-h-0 flex-col"`
  - L214: `<div className="flex min-h-0 flex-1 flex-col">`

### pages/tabs/OverviewTab.tsx

- score: **80**
- bucket: **must_audit**
- area: **pages**
- lines: **465**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 12, count: 4)
  - L398: `- aside должен иметь overflow-hidden для vertical clipping`
  - L400: `- Но CSS spec запрещает overflow-x: visible + overflow-y: hidden`
  - L405: `aside внутри с overflow-hidden — clip только своё содержимое.`
  - L414: `className="flex h-full min-h-0 w-full flex-col overflow-hidden px-1 pb-2"`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L96: `style={{ minHeight: "7rem", maxHeight: "14rem" }}`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 3)
  - L348: `className="relative grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(0,2.2fr)_minmax(320px,360px)] xl:grid-rows-[minmax(0,1fr)]"`
  - L411: `className="relative hidden min-h-0 xl:block xl:h-full"`
  - L452: `<div className="xl:hidden">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 8)
  - L59: `<div className="min-w-0">`
  - L348: `className="relative grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(0,2.2fr)_minmax(320px,360px)] xl:grid-rows-[minmax(0,1fr)]"`
  - L351: `<div className="flex min-w-0 min-h-0 flex-col gap-4">`
  - L367: `<div className="flex min-h-0 flex-1 flex-col">`
  - L377: `<div className="min-h-0 flex-1">`

### pages/tabs/ReportTab.tsx

- score: **80**
- bucket: **must_audit**
- area: **pages**
- lines: **382**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L235: `<div className="grid grid-cols-1 gap-4 md:grid-cols-3">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L237: `title="DD Grid"`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L204: `<div className="flex min-h-[360px] flex-col items-center justify-center">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L235: `<div className="grid grid-cols-1 gap-4 md:grid-cols-3">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 2)
  - L53: `<div className="card-surface card-surface-hover flex h-full flex-col justify-between p-4">`
  - L60: `<div className="min-w-0">`

### pages/tenant-admin/tabs/LogsTab.tsx

- score: **80**
- bucket: **must_audit**
- area: **pages**
- lines: **452**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 13, count: 5)
  - L207: `<div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden px-5 pb-5 pt-4">`
  - L361: `<div className={'${SECTION_CARD} flex min-h-0 flex-1 overflow-hidden'}>`
  - L389: `<div className="flex min-h-0 min-w-0 flex-col overflow-hidden xl:border-r xl:border-[var(--border-subtle)]">`
  - L407: `<aside className="hidden min-h-0 overflow-hidden bg-[var(--bg-elevated-soft)] xl:flex xl:flex-col">`
  - L435: `<div className={'${SECTION_CARD} shrink-0 overflow-hidden xl:hidden'}>`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 12, count: 2)
  - L236: `className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-7"`
  - L332: `<div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-4">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 10, count: 5)
  - L236: `className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-7"`
  - L332: `<div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-4">`
  - L388: `<div className="grid h-full w-full grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px]">`
  - L407: `<aside className="hidden min-h-0 overflow-hidden bg-[var(--bg-elevated-soft)] xl:flex xl:flex-col">`
  - L435: `<div className={'${SECTION_CARD} shrink-0 overflow-hidden xl:hidden'}>`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 9, count: 10)
  - L207: `<div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden px-5 pb-5 pt-4">`
  - L361: `<div className={'${SECTION_CARD} flex min-h-0 flex-1 overflow-hidden'}>`
  - L363: `<div className="flex h-full w-full items-center justify-center text-[var(--text-muted)]">`
  - L368: `<div className="flex h-full w-full items-center justify-center p-5 text-center">`
  - L384: `<div className="flex h-full w-full items-center justify-center text-sm text-[var(--text-muted)]">`

### pages/DealPage.tsx

- score: **79**
- bucket: **should_audit**
- area: **pages**
- lines: **587**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 12, count: 4)
  - L267: `<div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--bg-card)]">`
  - L290: `<div className="flex min-h-0 flex-1 overflow-hidden">`
  - L382: `<main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">`
  - L470: `className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-4 lg:p-6"`
- [LOCAL_X_SCROLL] Есть локальный horizontal scroll — вероятно data-heavy surface (weight: 9, count: 1)
  - L408: `className="flex overflow-x-auto border-t border-[var(--border)] pt-3"`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 14, count: 2)
  - L54: `dd_grid: "DD Grid",`
  - L221: `"DD Grid пока недоступен",`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 3)
  - L268: `<header className="hidden shrink-0 border-b border-[var(--border)] bg-[var(--bg-card)] lg:block">`
  - L291: `<aside className="hidden min-h-0 shrink-0 lg:flex lg:w-60 lg:flex-col lg:border-r lg:border-[var(--border)] lg:bg-[var(--bg-card)]">`
  - L383: `<header className="shrink-0 border-b border-[var(--border)] bg-[var(--bg-card)] lg:hidden">`
- [TAB_NAV] Есть tabs/tablist — важно для mobile nav и keyboard behavior (weight: 9, count: 1)
  - L566: `aria-selected={isActive}`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 8)
  - L267: `<div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--bg-card)]">`
  - L271: `<div className="min-w-0">`
  - L290: `<div className="flex min-h-0 flex-1 overflow-hidden">`
  - L291: `<aside className="hidden min-h-0 shrink-0 lg:flex lg:w-60 lg:flex-col lg:border-r lg:border-[var(--border)] lg:bg-[var(--bg-card)]">`
  - L293: `className="flex h-full flex-col overflow-y-auto overscroll-contain px-3 py-4"`

### components/evidence/EvidencePanel.tsx

- score: **78**
- bucket: **should_audit**
- area: **components**
- lines: **664**

- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 13, count: 5)
  - L253: `<div className="grid flex-1 grid-cols-1 gap-4 overflow-y-auto overflow-x-hidden px-5 py-4 md:grid-cols-3 md:overflow-hidden">        {/* Левая колонка */}`
  - L342: `<div className="col-span-1 flex flex-col gap-3 overflow-hidden">`
  - L395: `<div className="flex min-h-0 flex-1 flex-col overflow-hidden">`
  - L517: `<div className="col-span-1 flex flex-col gap-3 overflow-hidden">`
  - L627: `<div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--bg-card)]">`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L635: `style={{ width: '${pct}%' }}`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L253: `<div className="grid flex-1 grid-cols-1 gap-4 overflow-y-auto overflow-x-hidden px-5 py-4 md:grid-cols-3 md:overflow-hidden">        {/* Левая колонка */}`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L400: `<table className="w-full text-[11px]">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L253: `<div className="grid flex-1 grid-cols-1 gap-4 overflow-y-auto overflow-x-hidden px-5 py-4 md:grid-cols-3 md:overflow-hidden">        {/* Левая колонка */}`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 6, count: 5)
  - L196: `<div className="min-w-0 space-y-1">`
  - L211: `className="h-auto min-h-0 px-0 py-0 text-[11px] font-medium text-[var(--accent-primary)] hover:bg-transparent hover:text-[var(--accent-primary)] hover:underline"`
  - L395: `<div className="flex min-h-0 flex-1 flex-col overflow-hidden">`
  - L465: `className="h-auto min-h-0 px-0 py-0 text-[11px] font-medium text-[var(--accent-primary)] hover:bg-transparent hover:text-[var(--accent-primary)] hover:underline"`
  - L630: `"h-full rounded-full",`

### pages/tabs/RequestsTab.tsx

- score: **78**
- bucket: **should_audit**
- area: **pages**
- lines: **565**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 16, count: 9)
  - L378: `<header className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
  - L465: `? "grid min-h-0 min-w-0 flex-1 items-start gap-4 overflow-hidden lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"`
  - L466: `: "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"`
  - L469: `<div className="flex min-h-0 min-w-0 flex-col overflow-hidden">`
  - L485: `className="min-w-0 self-start overflow-hidden pr-4"`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L98: `<div className="flex min-h-[320px] flex-col items-center justify-center px-6 py-10 text-center">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 2)
  - L465: `? "grid min-h-0 min-w-0 flex-1 items-start gap-4 overflow-hidden lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"`
  - L509: `? "grid min-h-0 min-w-0 flex-1 items-start gap-4 overflow-hidden lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 10, count: 15)
  - L72: `<div className="min-w-0">`
  - L375: `className="flex h-full min-h-0 flex-col"`
  - L378: `<header className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
  - L379: `<div className="flex min-h-0 flex-1 flex-col px-5">`
  - L459: `<div className="flex min-h-0 flex-1 flex-col py-4">`

### pages/tabs/overview/LaunchWideOverlay.tsx

- score: **76**
- bucket: **should_audit**
- area: **pages**
- lines: **463**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L383: `<section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L381: `style={{ width: overlayWidth }}`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L380: `className="absolute bottom-0 top-0 z-30 hidden xl:block right-[calc(100%+16px)]"`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 8)
  - L51: `"flex min-w-0 min-h-0 flex-col border-r border-[var(--border-soft)] bg-[var(--bg-elevated-soft)]";`
  - L57: `"min-w-0 min-h-0 flex-1 overflow-y-auto px-5 py-4";`
  - L60: `"min-w-0 min-h-0 overflow-y-auto bg-[var(--bg-card)]";`
  - L138: `<div className="min-w-0">`
  - L383: `<section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">`

### pages/tenant-admin/sections/project-drilldown/ProjectOverviewSection.tsx

- score: **76**
- bucket: **should_audit**
- area: **pages**
- lines: **378**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L259: `<div className="inline-flex overflow-hidden rounded-xl border border-[var(--border)] text-[11px]">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 13, count: 3)
  - L92: `<div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">`
  - L156: `<div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">`
  - L285: `<div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 14, count: 2)
  - L178: `<table className="w-full min-w-[560px] border-collapse">`
  - L323: `<table className="w-full min-w-[860px] border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 9, count: 3)
  - L178: `<table className="w-full min-w-[560px] border-collapse">`
  - L316: `<div className="flex min-h-[120px] items-center justify-center px-5 py-6 text-sm text-[var(--text-muted)]">`
  - L323: `<table className="w-full min-w-[860px] border-collapse">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 3)
  - L92: `<div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">`
  - L156: `<div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">`
  - L285: `<div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 4, count: 1)
  - L248: `<div className="min-w-0">`

### pages/tabs/dd-grid-v1/DDGridV1TypedGroups.tsx

- score: **74**
- bucket: **should_audit**
- area: **pages**
- lines: **410**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L382: `style={{ height: estimateGroupMatrixHeightPx(group.reviewRows.length) }}`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 37)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1TypedGroups.tsx`
  - L3: `// Orchestration-компонент для multi-table view DD Grid V1.`
  - L10: `//     - buildDDGridV1TypedGroups()  — по одной таблице на doc_type`
  - L12: `//     - buildDDGridV1AllDocumentsGroup() — одна таблица со всеми`
  - L21: `// - агрегирует selection из нескольких DDGridV1Matrix,`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 3)
  - L353: `<div className="h-full min-h-0">`
  - L377: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pr-1">`
  - L381: `className="min-h-0 shrink-0"`

### pages/tabs/overview/ProjectDomainsOverviewPanel.tsx

- score: **74**
- bucket: **should_audit**
- area: **pages**
- lines: **257**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L215: `<div className="grid grid-cols-1 gap-2 px-5 pb-3 sm:grid-cols-3">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L89: `className="pointer-events-none absolute inset-y-0 left-0 w-[3px] rounded-l-2xl bg-[var(--accent-primary)] xl:rounded-bl-none"`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L215: `<div className="grid grid-cols-1 gap-2 px-5 pb-3 sm:grid-cols-3">`

### App.tsx

- score: **73**
- bucket: **should_audit**
- area: **routing**
- lines: **548**

- [ROOT_APP] Корневой routing/layout файл приложения (weight: 40, count: 1)
- [ROUTE_HEAVY] Много route-объявлений в одном файле (weight: 24, count: 63)
- [VIEWPORT_CONTRACT] Есть viewport-bound высота (h-screen / dvh / 100vh / min-h-screen) — важно для shell/mobile (weight: 9, count: 1)
  - L195: `- Marketing mode: wrapper grows to content (min-h-screen from CSS)`

### pages/tabs/dd-grid-v1/DDGridV1Matrix.tsx

- score: **73**
- bucket: **should_audit**
- area: **pages**
- lines: **1400**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 11, count: 3)
  - L1310: `"flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm transition-all duration-300",`
  - L1325: `<div className="min-h-0 flex-1 overflow-hidden">`
  - L1353: `<div className="flex h-full flex-col overflow-hidden rounded-l-2xl border-l border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 47)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1Matrix.tsx`
  - L3: `// V1-specific матрица DD Grid.`
  - L15: `import { AgGridReact } from "ag-grid-react";`
  - L25: `} from "ag-grid-community";`
  - L29: `DDGridV1CellState,`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 9)
  - L366: `<div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">`
  - L407: `<div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">`
  - L449: `<div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">`
  - L484: `<div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">`
  - L1310: `"flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm transition-all duration-300",`

### pages/tabs/overview/LaunchFormPanel.tsx

- score: **70**
- bucket: **should_audit**
- area: **pages**
- lines: **607**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L13: `const SECONDARY_ACTION_BUTTON_CLASS = "w-[220px] shrink-0 justify-center";`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 3)
  - L346: `<div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">`
  - L371: `<div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">`
  - L405: `<div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 6, count: 5)
  - L333: `<div className="flex h-full min-h-0 flex-col bg-[var(--bg-card)]">`
  - L343: `<div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">`
  - L347: `<div className="min-w-0">`
  - L372: `<div className="min-w-0">`
  - L406: `<div className="min-w-0">`

### pages/AdminPlaybookLinesPage.tsx

- score: **69**
- bucket: **should_audit**
- area: **pages**
- lines: **934**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [VIEWPORT_CONTRACT] Есть viewport-bound высота (h-screen / dvh / 100vh / min-h-screen) — важно для shell/mobile (weight: 9, count: 1)
  - L895: `<div className="min-h-screen bg-[var(--bg-base)] px-4 py-6">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L508: `<div className="grid grid-cols-1 gap-4 lg:grid-cols-3">`
- [LOCAL_X_SCROLL] Есть локальный horizontal scroll — вероятно data-heavy surface (weight: 9, count: 1)
  - L700: `<div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-card)]">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L701: `<table className="w-full table-fixed border-collapse text-[11px]">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 2)
  - L508: `<div className="grid grid-cols-1 gap-4 lg:grid-cols-3">`
  - L596: `<div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">`

### pages/tabs/dd-grid-v1/DDGridV1Drawer.tsx

- score: **67**
- bucket: **should_audit**
- area: **pages**
- lines: **829**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 26)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1Drawer.tsx`
  - L10: `DDGridV1DrawerContentDTO,`
  - L18: `buildDDGridV1DrawerFieldViews,`
  - L19: `normalizeDDGridV1EvidenceItems,`
  - L20: `resolveDDGridV1DrawerReason,`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 8, count: 2)
  - L26: `} from "./ddGridV1.drawer";`
  - L814: `V1 drawer · check_id: {drawerContent.check_id}`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 3)
  - L295: `<div className="min-w-0 flex-1">`
  - L514: `className="flex h-full w-full flex-col"`
  - L518: `<div className="min-w-0">`

### pages/tabs/dd-grid-v1/DDGridV1InstructionDrawer.tsx

- score: **66**
- bucket: **should_audit**
- area: **pages**
- lines: **185**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 10)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1InstructionDrawer.tsx`
  - L5: `// из уже загруженной DDGridV1DerivedModel.`
  - L11: `DDGridV1InstructionSnapshotDTO,`
  - L12: `DDGridV1CheckSummaryDTO,`
  - L19: `checks: DDGridV1CheckSummaryDTO[];`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 7, count: 1)
  - L3: `// Side-panel drawer со списком проверок doc_type, зафиксированных`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 2)
  - L103: `<aside className="flex h-full w-full flex-col">`
  - L124: `<div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">`

### pages/TenantAdminPage.tsx

- score: **65**
- bucket: **should_audit**
- area: **pages**
- lines: **408**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 10, count: 2)
  - L232: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5 xl:col-span-3">`
  - L303: `className={'${SECTION_CARD} flex min-h-0 flex-1 flex-col overflow-hidden'}`
- [VIEWPORT_CONTRACT] Есть viewport-bound высота (h-screen / dvh / 100vh / min-h-screen) — важно для shell/mobile (weight: 9, count: 1)
  - L221: `<div className="sticky top-0 h-screen w-full">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L218: `<div className="h-full xl:grid xl:grid-cols-4">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 2)
  - L218: `<div className="h-full xl:grid xl:grid-cols-4">`
  - L220: `<aside className="hidden xl:block xl:col-span-1">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 8)
  - L176: `<div className="flex h-full items-center justify-center">`
  - L187: `<div className="flex h-full items-center justify-center px-4">`
  - L218: `<div className="h-full xl:grid xl:grid-cols-4">`
  - L226: `className="h-full w-full object-cover"`
  - L232: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5 xl:col-span-3">`

### index.css

- score: **64**
- bucket: **should_audit**
- area: **global-styles**
- lines: **886**

- [GLOBAL_CSS] Глобальные стили, влияющие на весь app (weight: 35, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 11, count: 3)
  - L351: `overflow-x: hidden;`
  - L381: `overflow: hidden;`
  - L867: `overflow: hidden !important;`
- [VIEWPORT_CONTRACT] Есть viewport-bound высота (h-screen / dvh / 100vh / min-h-screen) — важно для shell/mobile (weight: 11, count: 3)
  - L344: `min-height: 100vh;`
  - L386: `min-h-screen on the wrapper. */`
  - L388: `min-height: 100vh;`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 7, count: 1)
  - L29: `--font-size-body-md:  1rem;       /* 16px — drawer body, review panels */`

### pages/tabs/overview/PipelineStepCard.tsx

- score: **64**
- bucket: **should_audit**
- area: **pages**
- lines: **277**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L124: `<div className="h-1 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">`
- [INLINE_SIZE_STYLE] Есть inline style с width/height/min/max — проверить необходимость (weight: 15, count: 1)
  - L127: `style={{ width: '${percent}%' }}`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 4, count: 1)
  - L178: `<div className="min-w-0 flex-1">`

### pages/tabs/dd-grid-v1/DDGridV1ViewModeToggle.tsx

- score: **63**
- bucket: **should_audit**
- area: **pages**
- lines: **69**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 13)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1ViewModeToggle.tsx`
  - L4: `// Использует format из useDDGridV1UIStore (matrix | list).`
  - L10: `useDDGridV1UIStore,`
  - L11: `type DDGridV1GridFormat,`
  - L12: `} from "./ddGridV1.collapseStore";`
- [TAB_NAV] Есть tabs/tablist — важно для mobile nav и keyboard behavior (weight: 9, count: 1)
  - L57: `aria-selected={format === option.value}`

### pages/tabs/dd-grid-v1/DDGridV1ViewSettings.tsx

- score: **63**
- bucket: **should_audit**
- area: **pages**
- lines: **184**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 19)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1ViewSettings.tsx`
  - L3: `// Панель настроек отображения DD Grid V1.`
  - L13: `// - все state читаются/пишутся через useDDGridV1UIStore.`
  - L19: `useDDGridV1UIStore,`
  - L20: `type DDGridV1ChecksScope,`
- [TAB_NAV] Есть tabs/tablist — важно для mobile nav и keyboard behavior (weight: 9, count: 1)
  - L119: `aria-selected={value === option.value}`

### pages/tenant-admin/tabs/ProjectsTab.tsx

- score: **63**
- bucket: **should_audit**
- area: **pages**
- lines: **73**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L42: `<table className="w-full min-w-[920px] border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 9, count: 3)
  - L11: `// - Table min-w-[920px]`
  - L38: `<div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">`
  - L42: `<table className="w-full min-w-[920px] border-collapse">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 2)
  - L36: `<div className="min-h-0 flex-1 overflow-auto">`
  - L38: `<div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">`

### pages/tenant-admin/tabs/UsersTab.tsx

- score: **63**
- bucket: **should_audit**
- area: **pages**
- lines: **79**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L48: `<table className="w-full min-w-[820px] border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 9, count: 3)
  - L11: `// - Table min-w-[820px] для readability на всех экранах`
  - L44: `<div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">`
  - L48: `<table className="w-full min-w-[820px] border-collapse">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 2)
  - L42: `<div className="min-h-0 flex-1 overflow-auto">`
  - L44: `<div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">`

### components/documents/pipeline/StructureStageViewer.tsx

- score: **61**
- bucket: **should_audit**
- area: **components**
- lines: **803**

- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 13, count: 5)
  - L322: `<aside className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">`
  - L376: `<section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">`
  - L395: `<section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">`
  - L529: `<div className="flex h-full min-h-0 flex-col overflow-hidden">`
  - L691: `<div className="flex h-full min-h-0 flex-col overflow-hidden">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L320: `<div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-3">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L208: `<div className="mb-3 h-[72px] border-b border-[var(--border-subtle)] pb-2">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L320: `<div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-3">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 10, count: 22)
  - L209: `<div className="flex h-full flex-col items-start justify-start">`
  - L320: `<div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-3">`
  - L322: `<aside className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">`
  - L330: `<div className="min-h-0 flex-1 overflow-auto px-1">`
  - L376: `<section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">`

### pages/tabs/GridTab.tsx

- score: **60**
- bucket: **should_audit**
- area: **pages**
- lines: **29**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 17, count: 5)
  - L3: `// Стабильная точка входа для вкладки DD Grid.`
  - L6: `// - вкладка полностью переведена на DD Grid V1 (dd-grid-v1 endpoint);`
  - L18: `import DDGridV1TabPage from "./dd-grid-v1/DDGridV1TabPage";`
  - L22: `return <DDGridV1TabPage {...props} />;`
- [DIALOG_MODAL] Есть dialog/modal/drawer поведение — важно для accessibility и layering (weight: 7, count: 1)
  - L9: `// - иерархические V1-заголовки матрицы и V1-drawer будут подключены`

### components/documents/pipeline/ChunksStageViewer.tsx

- score: **58**
- bucket: **should_audit**
- area: **components**
- lines: **1252**

- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 10, count: 2)
  - L376: `<section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)]">`
  - L917: `<div className="grid h-full min-h-0 auto-rows-fr grid-cols-1 gap-4 overflow-hidden xl:grid-cols-3 xl:grid-rows-1">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L917: `<div className="grid h-full min-h-0 auto-rows-fr grid-cols-1 gap-4 overflow-hidden xl:grid-cols-3 xl:grid-rows-1">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L357: `<div className="mb-3 h-[72px] border-b border-[var(--border-subtle)] pb-2">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L917: `<div className="grid h-full min-h-0 auto-rows-fr grid-cols-1 gap-4 overflow-hidden xl:grid-cols-3 xl:grid-rows-1">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 10, count: 18)
  - L358: `<div className="flex h-full flex-col items-start justify-start">`
  - L376: `<section className="min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)]">`
  - L377: `<div className="flex h-full min-h-0 flex-col px-3 pt-3">`
  - L379: `<div className="min-h-0 flex-1 overflow-auto pb-3">{children}</div>`
  - L824: `<div className="flex h-full min-h-0 flex-col gap-3">`

### components/settings/ProjectMembersPanel.tsx

- score: **58**
- bucket: **should_audit**
- area: **components**
- lines: **604**

- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L263: `<section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">`
- [LOCAL_X_SCROLL] Есть локальный horizontal scroll — вероятно data-heavy surface (weight: 9, count: 1)
  - L303: `<div className="overflow-x-auto">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L304: `<table className="w-full border-collapse">`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L213: `<div className="flex min-h-[280px] flex-col items-center justify-center text-center">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L399: `<div className="grid gap-4 md:grid-cols-2">`

### pages/instructions/DocTypeDetailPage.tsx

- score: **58**
- bucket: **should_audit**
- area: **pages**
- lines: **936**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L826: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 12, count: 2)
  - L101: `<div className="grid grid-cols-3 gap-2 border-t border-[var(--border-soft)] pt-3">`
  - L878: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 10, count: 4)
  - L559: `<div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">`
  - L661: `<div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">`
  - L694: `<div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">`
  - L878: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 9, count: 11)
  - L297: `<div className="min-w-0 flex-1">`
  - L554: `<div className="flex min-h-0 flex-1 flex-col gap-4">`
  - L560: `<div className="min-w-0">`
  - L610: `<section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">`
  - L620: `<pre className="min-h-0 flex-1 overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-3 text-[11px] font-mono leading-relaxed text-[var(--text-primary)]">`

### pages/instructions/GlobalInstructionDetailPage.tsx

- score: **58**
- bucket: **should_audit**
- area: **pages**
- lines: **997**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L883: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 12, count: 2)
  - L141: `<div className="grid grid-cols-3 gap-2 border-t border-[var(--border-soft)] pt-3">`
  - L940: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 10, count: 4)
  - L598: `<div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">`
  - L700: `<div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">`
  - L733: `<div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">`
  - L940: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 9, count: 11)
  - L336: `<div className="min-w-0 flex-1">`
  - L593: `<div className="flex min-h-0 flex-1 flex-col gap-4">`
  - L599: `<div className="min-w-0">`
  - L649: `<section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">`
  - L659: `<pre className="min-h-0 flex-1 overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-3 text-[11px] font-mono leading-relaxed text-[var(--text-primary)]">`

### pages/PlaybooksRegistryPage.tsx

- score: **58**
- bucket: **should_audit**
- area: **pages**
- lines: **774**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 11, count: 1)
  - L670: `<div className="grid grid-cols-2 gap-3 sm:grid-cols-4">`
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 13, count: 1)
  - L292: `parts.push('<table>');`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 2)
  - L533: `<div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(300px,1fr)_2fr]">`
  - L670: `<div className="grid grid-cols-2 gap-3 sm:grid-cols-4">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 7, count: 6)
  - L93: `<div className="min-w-0">`
  - L441: `<div className="h-full overflow-y-auto overscroll-contain">`
  - L447: `<div className="min-w-0">`
  - L582: `<div className="min-w-0 flex-1">`
  - L649: `<div className="min-w-0">`

### pages/tabs/dd-grid-v1/DDGridV1ExportLayoutPicker.tsx

- score: **58**
- bucket: **should_audit**
- area: **pages**
- lines: **510**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 9)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1ExportLayoutPicker.tsx`
  - L14: `export type DDGridV1MatrixLayout = "single" | "byDocument" | "byScopeGroup";`
  - L16: `export interface DDGridV1ExportLayoutPickerProps {`
  - L19: `onApply: (layout: DDGridV1MatrixLayout) => void;`
  - L27: `id: DDGridV1MatrixLayout;`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 4, count: 1)
  - L480: `<div className="min-w-0 flex-1">`

### pages/tabs/SettingsTab.tsx

- score: **56**
- bucket: **should_audit**
- area: **pages**
- lines: **266**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L112: `<div className="flex min-h-[280px] flex-col items-center justify-center text-center">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L191: `<div className="grid gap-4 xl:grid-cols-2">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 2)
  - L49: `<div className="min-w-0 flex-1">`
  - L240: `<div className="min-w-0 flex-1">`

### pages/tenant-instructions/TenantBaseDocTypeDetailPage.tsx

- score: **55**
- bucket: **should_audit**
- area: **pages**
- lines: **506**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L423: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 12, count: 2)
  - L125: `<div className="grid grid-cols-3 gap-2 border-t border-[var(--border-soft)] pt-3">`
  - L459: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L459: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 9)
  - L187: `<div className="min-w-0 flex-1">`
  - L334: `<div className="flex min-h-0 flex-1 flex-col gap-4">`
  - L336: `<section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">`
  - L352: `<pre className="min-h-0 flex-1 overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-3 text-[11px] font-mono leading-relaxed text-[var(--text-primary)]">`
  - L357: `<section className="flex min-h-0 flex-1 items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated-soft)] p-10 text-center">`

### pages/tenant-instructions/TenantBaseGlobalCheckDetailPage.tsx

- score: **55**
- bucket: **should_audit**
- area: **pages**
- lines: **464**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 9, count: 1)
  - L387: `<div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5">`
- [DENSE_GRID] Есть grid-cols-3+ — проверить mobile-first дисциплину (weight: 12, count: 2)
  - L86: `<div className="grid grid-cols-3 gap-2 border-t border-[var(--border-soft)] pt-3">`
  - L423: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 8, count: 1)
  - L423: `<div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 9)
  - L148: `<div className="min-w-0 flex-1">`
  - L295: `<div className="flex min-h-0 flex-1 flex-col gap-4">`
  - L297: `<section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">`
  - L313: `<pre className="min-h-0 flex-1 overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-3 text-[11px] font-mono leading-relaxed text-[var(--text-primary)]">`
  - L318: `<section className="flex min-h-0 flex-1 items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated-soft)] p-10 text-center">`

### pages/tabs/dd-grid-v1/DDGridV1ExportButtons.tsx

- score: **54**
- bucket: **should_audit**
- area: **pages**
- lines: **181**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 18, count: 14)
  - L2: `// src/pages/tabs/dd-grid-v1/DDGridV1ExportButtons.tsx`
  - L15: `import type { DDGridV1DerivedModel } from "./ddGridV1.types";`
  - L17: `buildDDGridV1ListExportTable,`
  - L18: `buildDDGridV1MatrixExportTable,`
  - L19: `} from "./ddGridV1.exportBuilder";`

### pages/tenant-admin/sections/project-drilldown/ProjectLogsSection.tsx

- score: **54**
- bucket: **should_audit**
- area: **pages**
- lines: **289**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [OVERFLOW_HIDDEN] Есть overflow-hidden / hidden overflow — проверить clipping и scroll ownership (weight: 12, count: 4)
  - L198: `className={'${SECTION_CARD} flex min-h-[420px] flex-1 overflow-hidden'}`
  - L223: `<div className="flex min-h-0 min-w-0 flex-col overflow-hidden xl:border-r xl:border-[var(--border-subtle)]">`
  - L242: `<aside className="hidden min-h-0 overflow-hidden bg-[var(--bg-elevated-soft)] xl:flex xl:flex-col">`
  - L271: `className={'${SECTION_CARD} mt-3 shrink-0 overflow-hidden xl:hidden'}`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 7, count: 1)
  - L198: `className={'${SECTION_CARD} flex min-h-[420px] flex-1 overflow-hidden'}`
- [BREAKPOINT_VISIBILITY] Есть breakpoint-driven visibility/layout logic — важен responsive audit (weight: 9, count: 3)
  - L222: `<div className="grid h-full w-full grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px]">`
  - L242: `<aside className="hidden min-h-0 overflow-hidden bg-[var(--bg-elevated-soft)] xl:flex xl:flex-col">`
  - L271: `className={'${SECTION_CARD} mt-3 shrink-0 overflow-hidden xl:hidden'}`
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 8, count: 8)
  - L131: `<div className="flex h-full min-h-0 flex-col px-5 pb-5 pt-4">`
  - L201: `<div className="flex h-full w-full items-center justify-center text-[var(--text-muted)]">`
  - L206: `<div className="flex h-full w-full items-center justify-center p-5 text-center">`
  - L222: `<div className="grid h-full w-full grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px]">`
  - L223: `<div className="flex min-h-0 min-w-0 flex-col overflow-hidden xl:border-r xl:border-[var(--border-subtle)]">`

### pages/tabs/overview/PipelinePreviewPanel.tsx

- score: **53**
- bucket: **should_audit**
- area: **pages**
- lines: **170**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [TAB_SCREEN] Tab/workspace screen (weight: 18, count: 1)
- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [FULL_HEIGHT_LAYOUT] Есть min-h-0 / min-w-0 / h-full — файл участвует в full-height app layout (weight: 5, count: 2)
  - L26: `<dt className="min-w-0 shrink-0 text-sm text-[var(--text-muted)]">`
  - L72: `<div className="min-w-0 text-[var(--text-primary)]">`

### pages/tenant-admin/components/LogsTable.tsx

- score: **53**
- bucket: **should_audit**
- area: **pages**
- lines: **133**

- [PAGE_ENTRY] Страничный app-компонент (weight: 18, count: 1)
- [DATA_HEAVY_NAME] По имени похож на data-heavy / admin / workspace файл (weight: 12, count: 1)
- [TABLE_OR_GRID] Есть таблица / grid / AG Grid — проверить adaptive behavior (weight: 14, count: 2)
  - L49: `<table`
- [FIXED_PX_UTILITY] Есть arbitrary px utility — проверить, не ломает ли responsive layout (weight: 9, count: 3)
  - L50: `className={'w-full ${compact ? "min-w-[720px]" : "min-w-[920px]"} border-collapse'}`
  - L98: `<div className={compact ? "max-w-[340px]" : "max-w-[400px]"}>`
  - L117: `<span className="inline-block max-w-[180px] truncate">`
