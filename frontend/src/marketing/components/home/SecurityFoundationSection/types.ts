// src/marketing/components/home/SecurityFoundationSection/types.ts

export type ClauseType =
  | "mac"
  | "liability"
  | "control"
  | "confidentiality"
  | "indemnity"
  | "warranty"
  | "termination"
  | "jurisdiction"
  | "reference"
  | "concept"
  | "general";

/** Фрагмент текста для заполнения силуэта (инфраструктурный термин или код) */
export type Fragment = {
  text: string;
  type: ClauseType;
  isKey: boolean;
};

export type RootSegment = {
  xStart: number;
  xEnd: number;
  width: number;
};

export type RootScanline = {
  y: number;
  segments: RootSegment[];
};

export type RootLine = {
  id: string;
  text: string;
  clauseType: ClauseType;
  isKey: boolean;
  targetX: number;
  targetY: number;
  width: number;
  fontSize: number;
  opacity: number;
  delay: number;
  colorTone: "primary" | "muted" | "accent";
};

export type SecurityPrinciple = {
  /** Внутренний id */
  id: string;
  /** Координата конца корня в процентах от размера контейнера */
  rootX: number;
  rootY: number;
  /** На какой стороне (left | right) показывать подпись */
  side: "left" | "right";
  /** Заголовок принципа */
  title: string;
  /** Объясняющая фраза */
  body: string;
};