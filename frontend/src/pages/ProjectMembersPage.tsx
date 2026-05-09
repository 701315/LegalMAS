// =============================================================
// src/pages/ProjectMembersPage.tsx
// Legacy/fallback route для управления участниками проекта.
// Основной UX теперь живёт внутри SettingsTab -> ProjectMembersPanel.
// Этот экран оставлен как совместимый route, но использует тот же content.
// =============================================================

import React from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Button from "../components/ui/Button";
import ProjectMembersPanel from "../components/settings/ProjectMembersPanel";

const ProjectMembersPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6 md:px-6">
      <div className="mx-auto max-w-6xl">
        <ProjectMembersPanel
          dealId={dealId}
          backButton={
            <Button
              type="button"
              size="sm"
              variant="secondary"
              leftIcon={<ArrowLeft size={14} />}
              onClick={() => navigate(`/projects/${dealId}?tab=settings`)}
            >
              Назад к настройкам проекта
            </Button>
          }
        />
      </div>
    </div>
  );
};

export default ProjectMembersPage;



