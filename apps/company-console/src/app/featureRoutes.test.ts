import { describe, expect, it } from "vitest";

import { companyFeatureRoutes } from "./featureRoutes";

describe("company feature route registry", () => {
  it("starts frozen and has no duplicate route paths", () => {
    expect(Object.isFrozen(companyFeatureRoutes)).toBe(true);
    expect(new Set(companyFeatureRoutes.map((route) => route.path)).size).toBe(
      companyFeatureRoutes.length,
    );
  });

  it("registers the hiring and evidence review feature routes", () => {
    expect(
      companyFeatureRoutes.map(({ path, title, ownerLane }) => ({
        path,
        title,
        ownerLane,
      })),
    ).toEqual([
      { path: "/hiring", title: "채용 캠페인", ownerLane: "A" },
      { path: "/review/report", title: "근거 보고서", ownerLane: "D" },
      { path: "/review/timeline", title: "면접 타임라인", ownerLane: "D" },
      { path: "/review/human", title: "사람 검토", ownerLane: "D" },
    ]);
    expect(companyFeatureRoutes.every((route) => route.element)).toBe(true);
  });
});
