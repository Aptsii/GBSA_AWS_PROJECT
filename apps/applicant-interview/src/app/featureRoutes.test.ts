import { describe, expect, it } from "vitest";

import { applicantFeatureRoutes } from "./featureRoutes";

describe("applicant feature route registry", () => {
  it("starts frozen and has no duplicate route paths", () => {
    expect(Object.isFrozen(applicantFeatureRoutes)).toBe(true);
    expect(
      new Set(applicantFeatureRoutes.map((route) => route.path)).size,
    ).toBe(applicantFeatureRoutes.length);
  });

  it("registers access, submission, equipment, and interview routes", () => {
    expect(
      applicantFeatureRoutes.map(({ path, title, ownerLane }) => ({
        path,
        title,
        ownerLane,
      })),
    ).toEqual([
      { path: "/access", title: "초대 및 동의", ownerLane: "A" },
      { path: "/submissions", title: "지원 자료 제출", ownerLane: "B" },
      { path: "/equipment-check", title: "장비 점검", ownerLane: "C" },
      { path: "/interview", title: "AI 면접실", ownerLane: "C" },
    ]);
    expect(applicantFeatureRoutes.every((route) => route.element)).toBe(true);
  });
});
