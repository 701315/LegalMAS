import { describe, expect, it } from "vitest";

import {
  resolveDDGridV1PresentationInfo,
} from "../../src/pages/tabs/dd-grid-v1/ddGridV1.drawer";

import type {
  DDGridV1DrawerContentDTO,
} from "../../src/types/dealReview";

function makeDrawer(
  overrides: Partial<DDGridV1DrawerContentDTO> = {},
): DDGridV1DrawerContentDTO {
  return {
    check_id: "liability_cap",
    check_name: "Liability cap",
    document_id: "doc-1",
    cell_state: "defined",
    reason: null,
    review_status: "needs_review",
    review_message: "Review the indemnity wording.",
    display_text: "No aggregate liability cap was found.",
    execution_status: "SUCCESS",
    detection_level: null,
    confidence: null,
    quality_flags: null,
    qc_status: null,
    qc_by: null,
    qc_at: null,
    qc_comment: null,
    agent_name: null,
    model_version: null,
    execution_time_ms: null,
    retry_attempts: null,
    input_tokens: null,
    output_tokens: null,
    fields: [],
    evidence_items: [],
    ...overrides,
  };
}

describe("resolveDDGridV1PresentationInfo", () => {
  it("показывает localized provenance для готового безопасного presentation", () => {
    const info = resolveDDGridV1PresentationInfo(
      makeDrawer({
        presentation_locale: "ru",
        presentation_status: "ready",
        presentation_is_fallback: false,
      }),
    );

    expect(info).toEqual({
      labelKey: "drawer.presentation.localized",
      tone: "success",
      interpolation: { locale: "ru" },
    });
  });

  it("показывает processing fallback для pending presentation", () => {
    const info = resolveDDGridV1PresentationInfo(
      makeDrawer({
        presentation_locale: "ru",
        presentation_status: "pending",
        presentation_is_fallback: true,
      }),
    );

    expect(info).toEqual({
      labelKey: "drawer.presentation.fallbackProcessing",
      tone: "warning",
    });
  });

  it("показывает stale fallback, не используя localized content как источник выбора", () => {
    const info = resolveDDGridV1PresentationInfo(
      makeDrawer({
        presentation_locale: "ru",
        presentation_status: "stale",
        presentation_is_fallback: true,
      }),
    );

    expect(info).toEqual({
      labelKey: "drawer.presentation.fallbackStale",
      tone: "warning",
    });
  });

  it("показывает failed fallback", () => {
    const info = resolveDDGridV1PresentationInfo(
      makeDrawer({
        presentation_locale: "ru",
        presentation_status: "failed",
        presentation_is_fallback: true,
      }),
    );

    expect(info).toEqual({
      labelKey: "drawer.presentation.fallbackFailed",
      tone: "error",
    });
  });

  it("не показывает provenance badge для legacy payload без presentation metadata", () => {
    const info = resolveDDGridV1PresentationInfo(
      makeDrawer(),
    );

    expect(info).toBeNull();
  });

  it("использует neutral canonical fallback для неизвестного backend status", () => {
    const info = resolveDDGridV1PresentationInfo(
      makeDrawer({
        presentation_status: "unknown_future_status",
        presentation_is_fallback: true,
      }),
    );

    expect(info).toEqual({
      labelKey: "drawer.presentation.fallbackCanonical",
      tone: "muted",
    });
  });
});
