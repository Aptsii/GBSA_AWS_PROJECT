export interface FeatureRoute {
  readonly path: string;
  readonly title: string;
  readonly ownerLane: "A" | "B" | "C";
}

export const applicantFeatureRoutes: readonly FeatureRoute[] = Object.freeze(
  [],
);
