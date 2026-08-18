import type {
  DeletionRequestCreate,
  DeletionStatus,
  FinalDecisionCreate,
  HumanAssessmentReviewCreate,
  HumanReviewView,
  ProcessingStatus,
  ReportView,
  ReviewArtifactCreate,
  TimelineView,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";

import { apiClient } from "../../app/api";

export interface ReviewApi {
  getReport(sessionId: string): Promise<ReportView | ProcessingStatus>;
  getTimeline(sessionId: string, query?: string): Promise<TimelineView>;
  createAssessmentReview(
    reportId: string,
    reportItemId: string,
    payload: HumanAssessmentReviewCreate,
  ): Promise<HumanReviewView>;
  createReviewArtifact(
    sessionId: string,
    payload: ReviewArtifactCreate,
  ): Promise<HumanReviewView>;
  recordFinalDecision(
    invitationId: string,
    payload: FinalDecisionCreate,
  ): Promise<HumanReviewView>;
  requestDeletion(payload: DeletionRequestCreate): Promise<DeletionStatus>;
  getDeletionStatus(deletionRequestId: string): Promise<DeletionStatus>;
}

export function createReviewApi(client: BrowserApiClient): ReviewApi {
  return {
    getReport(sessionId) {
      return client.get<ReportView | ProcessingStatus>(
        `/interview-sessions/${sessionId}/report`,
        { auth: "company" },
      );
    },
    getTimeline(sessionId, query) {
      const normalizedQuery = query?.trim();
      const suffix = normalizedQuery
        ? `?query=${encodeURIComponent(normalizedQuery)}`
        : "";
      return client.get<TimelineView>(
        `/interview-sessions/${sessionId}/timeline${suffix}`,
        { auth: "company" },
      );
    },
    createAssessmentReview(reportId, reportItemId, payload) {
      return client.post<HumanReviewView, HumanAssessmentReviewCreate>(
        `/reports/${reportId}/items/${reportItemId}/reviews`,
        payload,
        { auth: "company" },
      );
    },
    createReviewArtifact(sessionId, payload) {
      return client.post<HumanReviewView, ReviewArtifactCreate>(
        `/interview-sessions/${sessionId}/review-artifacts`,
        payload,
        { auth: "company" },
      );
    },
    recordFinalDecision(invitationId, payload) {
      return client.post<HumanReviewView, FinalDecisionCreate>(
        `/invitations/${invitationId}/final-decisions`,
        payload,
        { auth: "company" },
      );
    },
    requestDeletion(payload) {
      return client.post<DeletionStatus, DeletionRequestCreate>(
        "/privacy/deletion-requests",
        payload,
        { auth: "company" },
      );
    },
    getDeletionStatus(deletionRequestId) {
      return client.get<DeletionStatus>(
        `/privacy/deletion-requests/${deletionRequestId}`,
        { auth: "company" },
      );
    },
  };
}

export const reviewApi = createReviewApi(apiClient);
