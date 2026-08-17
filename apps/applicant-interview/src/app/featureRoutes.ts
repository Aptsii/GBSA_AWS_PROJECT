import { createElement, ReactElement } from "react";

import { ApplicantAccessJourney } from "../features/access";
import { EquipmentCheck } from "../features/interview/EquipmentCheck";
import { InterviewRoom } from "../features/interview/InterviewRoom";
import { SubmissionJourney } from "../features/submissions";

export interface FeatureRoute {
  readonly path: string;
  readonly title: string;
  readonly ownerLane: "A" | "B" | "C";
  readonly element: ReactElement;
}

export const applicantFeatureRoutes: readonly FeatureRoute[] = Object.freeze([
  {
    path: "/access",
    title: "초대 및 동의",
    ownerLane: "A",
    element: createElement(ApplicantAccessJourney),
  },
  {
    path: "/submissions",
    title: "지원 자료 제출",
    ownerLane: "B",
    element: createElement(SubmissionJourney),
  },
  {
    path: "/equipment-check",
    title: "장비 점검",
    ownerLane: "C",
    element: createElement(EquipmentCheck),
  },
  {
    path: "/interview",
    title: "AI 면접실",
    ownerLane: "C",
    element: createElement(InterviewRoom, {
      question: "최근 경험에서 맡은 역할과 결과를 구체적으로 설명해 주세요.",
      textOnly: true,
    }),
  },
]);
