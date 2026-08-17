import { describe, expect, it } from "vitest";

import { companyFeatureRoutes } from "./featureRoutes";

describe("company feature route registry", () => {
  it("starts frozen and has no duplicate route paths", () => {
    expect(Object.isFrozen(companyFeatureRoutes)).toBe(true);
    expect(new Set(companyFeatureRoutes.map((route) => route.path)).size).toBe(
      companyFeatureRoutes.length,
    );
  });
});
