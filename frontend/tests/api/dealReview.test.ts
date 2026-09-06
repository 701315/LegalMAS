import { describe, expect, it } from "vitest";

import { dealReviewKeys } from "../../src/api/dealReview";

describe("dealReviewKeys locale isolation", () => {
  it("создаёт разные DD Grid cache keys для разных presentation locales", () => {
    const enKey = dealReviewKeys.ddGridV1(
      "deal-1",
      "run-1",
      "en",
    );

    const ruKey = dealReviewKeys.ddGridV1(
      "deal-1",
      "run-1",
      "ru",
    );

    expect(enKey).toEqual([
      "deal-review",
      "dd-grid-v1",
      "deal-1",
      "run-1",
      "en",
    ]);

    expect(ruKey).toEqual([
      "deal-review",
      "dd-grid-v1",
      "deal-1",
      "run-1",
      "ru",
    ]);

    expect(enKey).not.toEqual(ruKey);
  });

  it("использует base key как prefix для всех locale variants одного run", () => {
    const baseKey = dealReviewKeys.ddGridV1Base(
      "deal-1",
      "run-1",
    );

    const localizedKey = dealReviewKeys.ddGridV1(
      "deal-1",
      "run-1",
      "en",
    );

    expect(baseKey).toEqual([
      "deal-review",
      "dd-grid-v1",
      "deal-1",
      "run-1",
    ]);

    expect(localizedKey.slice(0, baseKey.length)).toEqual(
      baseKey,
    );
  });

  it("разделяет progress keys между presentation locales", () => {
    const enKey = dealReviewKeys.resultPresentationProgress(
      "deal-1",
      "run-1",
      "en",
    );

    const ruKey = dealReviewKeys.resultPresentationProgress(
      "deal-1",
      "run-1",
      "ru",
    );

    expect(enKey).toEqual([
      "deal-review",
      "result-presentation-progress",
      "deal-1",
      "run-1",
      "en",
    ]);

    expect(ruKey).toEqual([
      "deal-review",
      "result-presentation-progress",
      "deal-1",
      "run-1",
      "ru",
    ]);

    expect(enKey).not.toEqual(ruKey);
  });

  it("нормализует пустую locale в null key segment", () => {
    const key = dealReviewKeys.ddGridV1(
      "deal-1",
      "run-1",
      "   ",
    );

    expect(key).toEqual([
      "deal-review",
      "dd-grid-v1",
      "deal-1",
      "run-1",
      null,
    ]);
  });
});
