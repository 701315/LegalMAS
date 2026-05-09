// =============================================================
// src/pages/tabs/GridTab.tsx
// Стабильная точка входа для вкладки DD Grid.
// Реализация вынесена в ./grid/GridTabPage без изменения внешнего API.
// =============================================================

import React from "react";

import GridTabPage from "./grid/GridTabPage";
import type { GridTabProps } from "./grid/gridTab.types";

export const GridTab: React.FC<GridTabProps> = (props) => {
  return <GridTabPage {...props} />;
};

export default GridTab;



