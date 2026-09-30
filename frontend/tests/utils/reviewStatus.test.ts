import { describe, expect, it } from "vitest";

import {
  classifyReviewStatus,
  isSkippableReviewStatus,
} from "../../src/utils/reviewStatus";

describe("classifyReviewStatus", () => {
  describe("legacy family (risk_detection / clause_presence)", () => {
    it("maps 'ok' to pass", () => {
      expect(classifyReviewStatus("ok")).toBe("pass");
    });
    it("maps 'no_issue_detected' to pass", () => {
      expect(classifyReviewStatus("no_issue_detected")).toBe("pass");
    });
    it("maps 'needs_review' to fail", () => {
      expect(classifyReviewStatus("needs_review")).toBe("fail");
    });
    it("maps 'unclear' to unclear", () => {
      expect(classifyReviewStatus("unclear")).toBe("unclear");
    });
    it("maps 'not_applicable' to skip", () => {
      expect(classifyReviewStatus("not_applicable")).toBe("skip");
    });
  });

  describe("v2 family (field_extraction)", () => {
    it("maps 'clause_defined' to pass", () => {
      expect(classifyReviewStatus("clause_defined")).toBe("pass");
    });
    it("maps 'clause_partially_defined' to unclear", () => {
      expect(classifyReviewStatus("clause_partially_defined")).toBe(
        "unclear",
      );
    });
    it("maps 'clause_missing' to fail", () => {
      expect(classifyReviewStatus("clause_missing")).toBe("fail");
    });
  });

  describe("edge cases", () => {
    it("returns 'skip' for null", () => {
      expect(classifyReviewStatus(null)).toBe("skip");
    });
    it("returns 'skip' for undefined", () => {
      expect(classifyReviewStatus(undefined)).toBe("skip");
    });
    it("returns 'skip' for empty string", () => {
      expect(classifyReviewStatus("")).toBe("skip");
    });
    it("returns 'skip' for whitespace-only", () => {
      expect(classifyReviewStatus("   \t\n")).toBe("skip");
    });
    it("returns 'skip' for unknown value", () => {
      expect(classifyReviewStatus("some_future_status")).toBe("skip");
    });
    it("is case-insensitive", () => {
      expect(classifyReviewStatus("CLAUSE_DEFINED")).toBe("pass");
      expect(classifyReviewStatus("Clause_Missing")).toBe("fail");
    });
    it("trims surrounding whitespace", () => {
      expect(classifyReviewStatus("  clause_defined  ")).toBe("pass");
    });
  });
});

describe("isSkippableReviewStatus", () => {
  it("returns true for null / empty / unknown / not_applicable", () => {
    expect(isSkippableReviewStatus(null)).toBe(true);
    expect(isSkippableReviewStatus("")).toBe(true);
    expect(isSkippableReviewStatus("future_status")).toBe(true);
    expect(isSkippableReviewStatus("not_applicable")).toBe(true);
  });
  it("returns false for known pass / fail / unclear", () => {
    expect(isSkippableReviewStatus("ok")).toBe(false);
    expect(isSkippableReviewStatus("clause_defined")).toBe(false);
    expect(isSkippableReviewStatus("clause_missing")).toBe(false);
    expect(isSkippableReviewStatus("clause_partially_defined")).toBe(false);
    expect(isSkippableReviewStatus("unclear")).toBe(false);
  });
});
