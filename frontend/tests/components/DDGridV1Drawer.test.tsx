import React from "react";
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  cleanup,
  render,
  screen,
} from "@testing-library/react";

import DDGridV1Drawer from "../../src/pages/tabs/dd-grid-v1/DDGridV1Drawer";

import type {
  DDGridV1DrawerContentDTO,
} from "../../src/types/dealReview";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (
        key === "drawer.presentation.localized" &&
        typeof options?.locale === "string"
      ) {
        return `Localized result: ${options.locale}`;
      }

      const translations: Record<string, string> = {
        "drawer.presentation.fallbackProcessing":
          "Original result shown; localization is in progress",
        "drawer.presentation.fallbackFailed":
          "Original result shown; localization was not generated",
        "drawer.presentation.fallbackStale":
          "Original result shown; localization is outdated",
        "drawer.presentation.fallbackMissing":
          "Original result shown; localization has not been requested",
        "drawer.presentation.fallbackCanonical":
          "Original result shown",
      };

      return translations[key] ?? key;
    },
    i18n: {
      language: "en",
    },
  }),
}));

vi.mock("../../src/api/qc", () => ({
  useUpdateReviewQc: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
  }),
}));

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

function renderDrawer(
  drawerContent: DDGridV1DrawerContentDTO,
) {
  return render(
    <DDGridV1Drawer
      open={true}
      onClose={vi.fn()}
      runId="run-1"
      documentId="doc-1"
      documentName="Agreement"
      drawerContent={drawerContent}
    />,
  );
}

afterEach(() => {
  cleanup();
});

describe("DDGridV1Drawer presentation provenance", () => {
  it("показывает локализованный provenance badge для safe ready presentation", () => {
    renderDrawer(
      makeDrawer({
        check_name: "Лимит ответственности",
        display_text: "Совокупный лимит ответственности не обнаружен.",
        review_message: "Проверьте формулировку indemnity.",
        presentation_locale: "ru",
        presentation_status: "ready",
        presentation_is_fallback: false,
        canonical_check_name: "Liability cap",
        canonical_display_text: "No aggregate liability cap was found.",
        canonical_review_message: "Review the indemnity wording.",
      }),
    );

    expect(
      screen.getByText("Localized result: ru"),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("heading", {
        name: "Лимит ответственности",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "Совокупный лимит ответственности не обнаружен.",
      ),
    ).toBeInTheDocument();

    expect(
      screen.queryByText("Liability cap"),
    ).not.toBeInTheDocument();

    expect(
      screen.queryByText(
        "No aggregate liability cap was found.",
      ),
    ).not.toBeInTheDocument();
  });

  it("показывает canonical fallback и processing badge для pending presentation", () => {
    renderDrawer(
      makeDrawer({
        presentation_locale: "ru",
        presentation_status: "pending",
        presentation_is_fallback: true,
      }),
    );

    expect(
      screen.getByText(
        "Original result shown; localization is in progress",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("heading", {
        name: "Liability cap",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "No aggregate liability cap was found.",
      ),
    ).toBeInTheDocument();
  });

  it("показывает stale fallback и не выводит badge для отсутствующей metadata одновременно", () => {
    const { rerender } = renderDrawer(
      makeDrawer({
        presentation_locale: "ru",
        presentation_status: "stale",
        presentation_is_fallback: true,
      }),
    );

    expect(
      screen.getByText(
        "Original result shown; localization is outdated",
      ),
    ).toBeInTheDocument();

    rerender(
      <DDGridV1Drawer
        open={true}
        onClose={vi.fn()}
        runId="run-1"
        documentId="doc-1"
        documentName="Agreement"
        drawerContent={makeDrawer()}
      />,
    );

    expect(
      screen.queryByText(
        "Original result shown; localization is outdated",
      ),
    ).not.toBeInTheDocument();

    expect(
      screen.queryByText("Original result shown"),
    ).not.toBeInTheDocument();
  });
});
