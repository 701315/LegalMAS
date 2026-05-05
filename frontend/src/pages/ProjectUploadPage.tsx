// =============================================================
// src/pages/ProjectUploadPage.tsx
// Загрузка документов в проект.
// Упрощённый UI в стиле workspace + explorer-like file list.
// =============================================================

// src/pages/ProjectUploadPage.tsx

import React from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import ProjectUploadPanel from "../components/upload/ProjectUploadPanel";

const ProjectUploadPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  return (
    <ProjectUploadPanel
      dealId={dealId}
      mode="page"
      onFinished={() => navigate(`/projects/${dealId}`)}
    />
  );
};

export default ProjectUploadPage;




