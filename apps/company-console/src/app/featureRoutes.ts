export interface FeatureRoute {
  readonly path: string;
  readonly title: string;
  readonly ownerLane: "A" | "D";
}

export const companyFeatureRoutes: readonly FeatureRoute[] = Object.freeze([
  { path: "/hiring", title: "채용 캠페인", ownerLane: "A" },
  { path: "/review/report", title: "근거 보고서", ownerLane: "D" },
  { path: "/review/timeline", title: "면접 타임라인", ownerLane: "D" },
  { path: "/review/human", title: "사람 검토", ownerLane: "D" },
]);
