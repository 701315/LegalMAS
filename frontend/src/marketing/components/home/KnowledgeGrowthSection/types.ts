// src/marketing/components/home/KnowledgeGrowthSection/types.ts

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

export type Fragment = {
  text: string;
  type: ClauseType;
  isKey: boolean;
};

export type FragmentBucket = {
  micro: Fragment[];
  short: Fragment[];
  medium: Fragment[];
  long: Fragment[];
};

export type ScanlineSegment = {
  xStart: number;
  xEnd: number;
  width: number;
};

export type Scanline = {
  y: number;
  segments: ScanlineSegment[];
};

export type TreeLine = {
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

