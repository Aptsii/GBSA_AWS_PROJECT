import { createElement, ReactElement } from "react";

import { HiringJourney } from "../features/hiring";
import { HumanReview } from "../features/review/HumanReview";
import { ReportView } from "../features/review/ReportView";
import { TimelineView } from "../features/review/TimelineView";

export interface FeatureRoute {
  readonly path: string;
  readonly title: string;
  readonly ownerLane: "A" | "D";
  readonly element: ReactElement;
}

export const companyFeatureRoutes: readonly FeatureRoute[] = Object.freeze([
  {
    path: "/hiring",
    title: "채용 캠페인",
    ownerLane: "A",
    element: createElement(HiringJourney),
  },
  {
    path: "/review/report",
    title: "근거 보고서",
    ownerLane: "D",
    element: createElement(ReportView, {
      summary: "면접이 완료되면 평가 기준별 Evidence가 여기에 표시됩니다.",
      items: [],
    }),
  },
  {
    path: "/review/timeline",
    title: "면접 타임라인",
    ownerLane: "D",
    element: createElement(TimelineView, { entries: [] }),
  },
  {
    path: "/review/human",
    title: "사람 검토",
    ownerLane: "D",
    element: createElement(HumanReview),
  },
]);
