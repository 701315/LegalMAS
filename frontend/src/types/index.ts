// =============================================================
// src/types/index.ts
// Центральный фасад экспортов типов.
// =============================================================

export type { PaginatedResponse, ApiError, JsonValue } from "./common";

export type {
  ClassificationLevel,
  ClassificationMetadata,
  ClassificationStats,
  ClassificationReport,
  DocumentStatus,
  ProcessingErrorDetails,
  Document,
  DocumentCompositionType,
  DocumentCompositionMeta,
  DocumentWithComposition,
  DocumentListItem,
  DocumentVersion,
  DocumentDetail,
  DocumentFamilyDto,
  DocumentFamily,
  ReclassifyInput,
  ReclassifyResult,
  ClauseNode,
  StructuredClauseTree,
  ExtractedValue,
  StructuredDataResult,
  OpenViewerAtPayload,
  OpenViewerAtFn,
  DocumentColumnId,
  DocumentColumnDef,
} from "./documents";

export { ALL_DOCUMENT_COLUMNS } from "./documents";

export * from "./dealReview";

export type {
  RunStatus,
  RunCreateInput,
  Run,
  ProgressEvent,
} from "./runs";

export type {
  CheckResultValue,
  SeverityLevel,
  QCStatus,
  CheckResultOrigin,
  CheckResultOriginType,
  CheckResult,
  StructuredField,
  Evidence,
} from "./checks";

export type {
  DealStatus,
  DealChecksMode,
  DealPrimaryLanguageUpdatePayload,
  Deal,
  DealDetail,
  ImportStatus,
  ImportJob,
} from "./deals";

export type {
  PlaybookLine,
  PlaybookVersionShort,
  PlaybookVersionDetail,
  PlaybookCreateResponse,
  PlaybookCheckInfo,
  PlaybookTopicInfo,
  PlaybookCreateRequest,
  ModelConfig,
  ModelConfigCreateInput,
  ModelConfigUpdateInput,
  DealPlaybookHistoryItem,
  PlaybookLineShort,
  PlaybookLineItemPayload,
  PlaybookLineDetail,
} from "./playbooks";

export type {
  PipelineStageCode,
  PipelineStageStatus,
  PipelineStageKind,
  StageViewMode,
  StageMetaDTO,
  StageProvenanceDTO,
  StageRepresentationDTO,
  PdfPreviewDTO,
  LayoutPagePreviewDTO,
  LayoutPreviewDTO,
  StructureSectionPreviewDTO,
  StructurePreviewDTO,
  ChunkPreviewDTO,
  ChunksPreviewDTO,
  PipelineStagePreview,
  PipelineStageViewDTO,
  DocumentPipelineViewResponseDTO,
} from "./pipeline";

export type { UserRole, User } from "./auth";

export type { DDRequest, DDRequestCreateInput } from "./ddRequests";

export type { ExportType, ExportRecord, AuditLogEntry } from "./exports";
