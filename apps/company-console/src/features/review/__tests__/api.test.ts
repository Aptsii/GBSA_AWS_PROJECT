import type {
  DeletionStatus,
  HumanReviewView,
  ReportView,
  TimelineView,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";
import { describe, expect, it, vi } from "vitest";

import { createReviewApi } from "../api";

describe("review API", () => {
  it("loads report and filtered timeline with company authorization", async () => {
    const report = { report_id: "report-1" } as ReportView;
    const timeline = { entries: [] } as unknown as TimelineView;
    const get = vi
      .fn()
      .mockResolvedValueOnce(report)
      .mockResolvedValueOnce(timeline);
    const api = createReviewApi({ get } as unknown as BrowserApiClient);

    await api.getReport("session-1");
    await api.getTimeline("session-1", "장애 복구");

    expect(get).toHaveBeenNthCalledWith(
      1,
      "/interview-sessions/session-1/report",
      {
        auth: "company",
      },
    );
    expect(get).toHaveBeenNthCalledWith(
      2,
      "/interview-sessions/session-1/timeline?query=%EC%9E%A5%EC%95%A0%20%EB%B3%B5%EA%B5%AC",
      { auth: "company" },
    );
  });

  it("records only explicit human review, decision and deletion commands", async () => {
    const review = { human_review_id: "review-1" } as HumanReviewView;
    const deletion = { deletion_request_id: "deletion-1" } as DeletionStatus;
    const post = vi
      .fn()
      .mockResolvedValueOnce(review)
      .mockResolvedValueOnce(review)
      .mockResolvedValueOnce(review)
      .mockResolvedValueOnce(deletion);
    const get = vi.fn().mockResolvedValue(deletion);
    const api = createReviewApi({ get, post } as unknown as BrowserApiClient);

    await api.createAssessmentReview("report-1", "item-1", {
      assessment_state: "needs_follow_up",
      reason: "추가 검증이 필요합니다.",
    });
    await api.createReviewArtifact("session-1", {
      review_type: "note",
      target_id: "item-1",
      value: "다음 면접에서 확인",
    });
    await api.recordFinalDecision("invitation-1", {
      decision: "hold",
      reason: "사람 검토 대기",
    });
    await api.requestDeletion({
      scope_type: "invitation",
      scope_id: "invitation-1",
      reason: "보관 목적 종료",
    });
    await api.getDeletionStatus("deletion-1");

    expect(post).toHaveBeenNthCalledWith(
      1,
      "/reports/report-1/items/item-1/reviews",
      {
        assessment_state: "needs_follow_up",
        reason: "추가 검증이 필요합니다.",
      },
      { auth: "company" },
    );
    expect(post).toHaveBeenNthCalledWith(
      3,
      "/invitations/invitation-1/final-decisions",
      { decision: "hold", reason: "사람 검토 대기" },
      { auth: "company" },
    );
    expect(get).toHaveBeenCalledWith("/privacy/deletion-requests/deletion-1", {
      auth: "company",
    });
  });
});
