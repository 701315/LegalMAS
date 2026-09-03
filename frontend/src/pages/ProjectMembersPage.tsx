// =============================================================
// src/pages/ProjectMembersPage.tsx
// Route для управления участниками проекта.
// Маршрут: /projects/:dealId/members
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Button from "../components/ui/Button";
import ProjectMembersPanel from "../components/settings/ProjectMembersPanel";

const ProjectMembersPage: React.FC = () => {
  const { t } = useTranslation("admin");
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  if (!dealId) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        <ProjectMembersPanel
          dealId={dealId}
          backButton={
            <Button
              type="button"
              size="sm"
              variant="secondary"
              leftIcon={<ArrowLeft size={14} />}
              onClick={() => navigate(`/projects/${dealId}`)}
            >
              {t("membersPage.backButton")}
            </Button>
          }
        />
      </div>
    </div>
  );
};

export default ProjectMembersPage;

