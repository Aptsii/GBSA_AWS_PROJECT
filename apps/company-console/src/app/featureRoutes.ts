export interface FeatureRoute {
  readonly path: string;
  readonly title: string;
  readonly ownerLane: "A" | "D";
}

export const companyFeatureRoutes: readonly FeatureRoute[] = Object.freeze([]);
