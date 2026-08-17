import { describe, expect, it } from "vitest";

import { applicantFeatureRoutes } from "./featureRoutes";

describe("applicant feature route registry", () => {
  it("starts frozen and has no duplicate route paths", () => {
    expect(Object.isFrozen(applicantFeatureRoutes)).toBe(true);
    expect(
      new Set(applicantFeatureRoutes.map((route) => route.path)).size,
    ).toBe(applicantFeatureRoutes.length);
  });
});
