// =============================================================
// src/pages/ModelConfigsAdminPage.tsx
// Админ-страница для управления профилями моделей (ModelConfig).
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";

import ModelConfigManagerPanel from "../components/model-config/ModelConfigManagerPanel";

const ModelConfigsAdminPage: React.FC = () => {
  const navigate = useNavigate();

  const params = new URLSearchParams(window.location.search);
  const dealIdFromQuery = params.get("dealId");

  return (
    <ModelConfigManagerPanel
      mode="page"
      dealId={dealIdFromQuery}
      onCancel={() => {
        if (dealIdFromQuery) {
          navigate(-1);
        } else {
          navigate("/admin");
        }
      }}
      onFinished={() => {
        if (dealIdFromQuery) {
          navigate(-1);
        }
      }}
    />
  );
};

export default ModelConfigsAdminPage;


