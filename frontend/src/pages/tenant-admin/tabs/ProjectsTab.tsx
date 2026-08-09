// =============================================================
// src/pages/tenant-admin/tabs/ProjectsTab.tsx
//
// Вкладка "Проекты" в admin panel. Двойное назначение:
// - Список проектов (selectedProjectId === null)
// - Drill down в проект (selectedProjectId !== null)
//
// Design contract:
// - Empty state если projects.length === 0
// - Sticky table header
// - Table min-w-[920px]
// - При selectedProjectId — рендерится ProjectDrillDown вместо таблицы
//
// State ownership:
// - selectedProjectId управляется в parent (main component),
//   потому что состояние выбранного проекта влияет на header rendering
//   (при drill down скрываются tabs)
// =============================================================

import React from "react";
import type { ProjectHealthDTO } from "../../../api/tenantAdmin";
import { LABEL_XS } from "../constants";
import ProjectRow from "../components/ProjectRow";

export interface ProjectsTabProps {
  /** Массив проектов для отображения */
  projects: ProjectHealthDTO[];
  /** Callback при клике на проект (открывает drill down) */
  onOpenProject: (dealId: string) => void;
}

const ProjectsTab: React.FC<ProjectsTabProps> = ({
  projects,
  onOpenProject,
}) => (
  <div className="min-h-0 flex-1 overflow-auto">
    {projects.length === 0 ? (
      <div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">
        Нет проектов
      </div>
    ) : (
      <table className="w-full min-w-[920px] border-collapse">
        <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
          <tr className="border-b border-[var(--border)]">
            <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Проект</th>
            <th className={`px-4 py-2.5 text-center ${LABEL_XS}`}>
              Документы
            </th>
            <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
              Последний анализ
            </th>
            <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Прогресс</th>
            <th className="w-24 px-4 py-2.5" />
          </tr>
        </thead>
        <tbody>
          {projects.map((p) => (
            <ProjectRow
              key={p.deal_id}
              project={p}
              onOpen={onOpenProject}
            />
          ))}
        </tbody>
      </table>
    )}
  </div>
);

export default ProjectsTab;


