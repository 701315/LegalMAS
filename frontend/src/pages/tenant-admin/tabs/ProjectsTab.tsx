// =============================================================
// src/pages/tenant-admin/tabs/ProjectsTab.tsx
//
// "Projects" tab in admin panel. Dual purpose:
// - Projects list (selectedProjectId === null)
// - Project drill down (selectedProjectId !== null)
//
// Design contract:
// - Empty state if projects.length === 0
// - Sticky table header
// - Table min-w-[920px]
// - When selectedProjectId is set — renders ProjectDrillDown instead of table
//
// State ownership:
// - selectedProjectId is managed in parent (main component),
//   because selected project state affects header rendering
//   (tabs are hidden during drill down)
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { ProjectHealthDTO } from "../../../api/tenantAdmin";
import { LABEL_XS } from "../constants";
import ProjectRow from "../components/ProjectRow";

export interface ProjectsTabProps {
  /** Array of projects to display */
  projects: ProjectHealthDTO[];
  /** Callback when clicking a project (opens drill down) */
  onOpenProject: (dealId: string) => void;
}

const ProjectsTab: React.FC<ProjectsTabProps> = ({
  projects,
  onOpenProject,
}) => {
  const { t } = useTranslation("tenantAdmin");

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      {projects.length === 0 ? (
        <div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">
          {t("projectsTab.noProjects")}
        </div>
      ) : (
        <table className="w-full min-w-[920px] border-collapse">
          <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
            <tr className="border-b border-[var(--border)]">
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("projectsTab.headers.project")}
              </th>
              <th className={`px-4 py-2.5 text-center ${LABEL_XS}`}>
                {t("projectsTab.headers.documents")}
              </th>
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("projectsTab.headers.lastAnalysis")}
              </th>
              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                {t("projectsTab.headers.progress")}
              </th>
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
};

export default ProjectsTab;


