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
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";

import ResultPresentationStatus from "../../src/pages/tabs/dd-grid-v1/ResultPresentationStatus";

const mocks = vi.hoisted(() => ({
  progressQuery: {
    data: null as Record<string, unknown> | null,
    isLoading: false,
    isError: false,
  },
  requestMutation: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("../../src/api/dealReview", () => ({
  dealReviewKeys: {
    ddGridV1Base: (dealId: string, runId: string) => [
      "deal-review",
      "dd-grid-v1",
      dealId,
      runId,
    ],
  },
  useResultPresentationProgress: vi.fn(() => mocks.progressQuery),
  useRequestResultPresentations: vi.fn(() => mocks.requestMutation),
}));

function makeProgress(
  overrides: Partial<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    run_id: "run-1",
    locale: "ru",
    content_version: "v1",
    total: 3,
    missing: 0,
    pending: 0,
    processing: 0,
    ready: 3,
    reviewed: 0,
    approved: 0,
    failed: 0,
    stale: 0,
    created_pending: 0,
    existing: 3,
    is_complete: true,
    dispatch_status: "dispatched",
    ...overrides,
  };
}

function renderStatus(canRequest = true) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const view = render(
    <QueryClientProvider client={queryClient}>
      <ResultPresentationStatus
        dealId="deal-1"
        runId="run-1"
        presentationLocale="ru"
        canRequest={canRequest}
      />
    </QueryClientProvider>,
  );

  return {
    ...view,
    queryClient,
  };
}

afterEach(() => {
  cleanup();
  mocks.progressQuery.data = null;
  mocks.progressQuery.isLoading = false;
  mocks.progressQuery.isError = false;
  mocks.requestMutation.mutate.mockReset();
  mocks.requestMutation.isPending = false;
  mocks.requestMutation.isError = false;
});

describe("ResultPresentationStatus", () => {
  it("разрешает editor/admin запросить отсутствующие локализованные результаты", async () => {
    mocks.progressQuery.data = makeProgress({
      missing: 3,
      ready: 0,
      existing: 0,
      is_complete: false,
    });

    renderStatus(true);

    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", {
        name: "v1Tab.presentations.requestButton",
      }),
    );

    expect(mocks.requestMutation.mutate).toHaveBeenCalledOnce();
    expect(mocks.requestMutation.mutate).toHaveBeenCalledWith("ru");
  });

  it("не показывает кнопку запроса пользователю без права на создание presentations", () => {
    mocks.progressQuery.data = makeProgress({
      missing: 3,
      ready: 0,
      existing: 0,
      is_complete: false,
    });

    renderStatus(false);

    expect(
      screen.queryByRole("button", {
        name: "v1Tab.presentations.requestButton",
      }),
    ).not.toBeInTheDocument();
  });

  it("показывает queued status и исключает повторный запрос во время batch", () => {
    mocks.progressQuery.data = makeProgress({
      pending: 2,
      ready: 1,
      is_complete: false,
    });

    renderStatus(true);

    expect(
      screen.getByText("v1Tab.presentations.queued"),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole("button", {
        name: "v1Tab.presentations.requestButton",
      }),
    ).not.toBeInTheDocument();
  });

  it("инвалидирует все locale variants DD Grid только после завершения active batch", async () => {
    mocks.progressQuery.data = makeProgress({
      pending: 1,
      ready: 2,
      is_complete: false,
    });

    const { queryClient, rerender } = renderStatus(true);
    const invalidateQueries = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);

    expect(invalidateQueries).not.toHaveBeenCalled();

    mocks.progressQuery.data = makeProgress({
      pending: 0,
      processing: 0,
      ready: 3,
      is_complete: true,
    });

    rerender(
      <QueryClientProvider client={queryClient}>
        <ResultPresentationStatus
          dealId="deal-1"
          runId="run-1"
          presentationLocale="ru"
          canRequest={true}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith({
        queryKey: [
          "deal-review",
          "dd-grid-v1",
          "deal-1",
          "run-1",
        ],
      });
    });
  });
});
