// =============================================================
// src/pages/tenant-admin/sections/project-drilldown/ProjectMembersSection.tsx
//
// Members sub-tab внутри ProjectDrillDown. Простая обёртка над
// ProjectMembersPanel — компонентом для управления участниками
// конкретного проекта (invite/remove/change role).
//
// Design contract:
// - Занимает всю доступную высоту parent (min-h-0 flex-1)
// - Scroll внутри секции (overflow-auto)
// - Padding по periметру
//
// Note: вся бизнес-логика в ProjectMembersPanel — эта секция
// только обеспечивает layout wrapper и scroll ownership.
// =============================================================

import React from "react";
import ProjectMembersPanel from "../../../../components/settings/ProjectMembersPanel";

export interface ProjectMembersSectionProps {
  /** ID проекта для которого показывать members */
  dealId: string;
}

const ProjectMembersSection: React.FC<ProjectMembersSectionProps> = ({
  dealId,
}) => (
  <div className="px-5 pb-5 pt-4">
    <ProjectMembersPanel dealId={dealId} />
  </div>
);

export default ProjectMembersSection;


