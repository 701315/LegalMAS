// src/pages/instructions/GlobalInstructionVersionDetailPage.tsx
//
// LEGACY REDIRECT.
//
// Ранее это была отдельная страница version-detail:
//   /admin/instructions/global-checks/:code/versions/:versionId
//
// В рамках UX-объединения детали инструкции и её версий вынесены
// на единую страницу с query param ?version=<id>:
//   /admin/instructions/global-checks/:code?version=<id>
//
// Этот компонент оставлен как redirect-layer, чтобы:
//   - существующие закладки продолжали работать,
//   - external ссылки не ломались,
//   - переход был прозрачным (replace: true).
//
// После нескольких релизов и подтверждённого отсутствия внешних
// ссылок этот файл + маршрут можно удалить.

import React from "react";
import { Navigate, useParams } from "react-router-dom";

const GlobalInstructionVersionDetailPage: React.FC = () => {
  const { instructionCode, versionId } = useParams<{
    instructionCode: string;
    versionId: string;
  }>();

  if (!instructionCode) {
    return <Navigate to="/admin/instructions/global-checks" replace />;
  }

  const target = versionId
    ? `/admin/instructions/global-checks/${instructionCode}?version=${versionId}`
    : `/admin/instructions/global-checks/${instructionCode}`;

  return <Navigate to={target} replace />;
};

export default GlobalInstructionVersionDetailPage;


