export interface FeatureRoute {
  readonly path: string;
  readonly title: string;
  readonly ownerLane: "A" | "B" | "C";
}

export const applicantFeatureRoutes: readonly FeatureRoute[] = Object.freeze(
  [
    { path: "/access", title: "초대 및 동의", ownerLane: "A" },
    { path: "/submissions", title: "지원 자료 제출", ownerLane: "B" },
    { path: "/equipment-check", title: "장비 점검", ownerLane: "C" },
    { path: "/interview", title: "AI 면접실", ownerLane: "C" },
  ],
);
