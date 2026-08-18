import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ReviewApi } from "../api";
import { HumanReview } from "../HumanReview";
import { ReportView } from "../ReportView";

describe("Evidence 검토 여정", () => {
  it("AI 원본과 사람 결정을 분리해 표시한다", () => {
    const onDecision = vi.fn();
    render(
      <>
        <ReportView
          summary="복구 역량 검토"
          items={[
            { id: "i1", criterion: "문제 해결", state: "needs_follow_up" },
          ]}
        />
        <HumanReview onDecision={onDecision} />
      </>,
    );
    expect(screen.getByText("AI 원본은 변경되지 않습니다.")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "보류 결정 기록" }));
    expect(onDecision).toHaveBeenCalledWith("hold");
  });

  it("실제 보고서를 불러오고 사람 평가를 append-only로 추가한다", async () => {
    const api = {
      createAssessmentReview: vi.fn().mockResolvedValue({
        created_at: "2026-08-18T00:00:00Z",
        created_by: "user-1",
        human_review_id: "review-1",
        review_type: "assessment_override",
      }),
      getReport: vi.fn().mockResolvedValue({
        ai_original_immutable: true,
        human_reviews: [],
        items: [
          {
            assessment_state: "needs_follow_up",
            criterion_id: "criterion-1",
            evidence: [],
            observation: "복구 절차를 설명했습니다.",
            rationale: "직접 근거가 제한적입니다.",
            report_item_id: "item-1",
            uncertainty: "실제 수행 여부 확인 필요",
          },
        ],
        report_id: "report-1",
        report_version: 1,
        status: "ready",
        summary: "복구 역량 검토",
      }),
    } as unknown as ReviewApi;
    render(<ReportView api={api} />);

    fireEvent.change(screen.getByLabelText("면접 세션 ID"), {
      target: { value: "session-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "보고서 불러오기" }));

    expect(await screen.findByText("복구 역량 검토")).toBeDefined();
    fireEvent.change(screen.getByLabelText("검토 이유 criterion-1"), {
      target: { value: "추가 검증이 필요합니다." },
    });
    fireEvent.click(screen.getByRole("button", { name: "사람 검토 추가" }));
    expect(api.createAssessmentReview).toHaveBeenCalledWith(
      "report-1",
      "item-1",
      expect.objectContaining({ reason: "추가 검증이 필요합니다." }),
    );
  });

  it("사람 최종 결정과 삭제 요청을 별도 API로 기록한다", async () => {
    const api = {
      getDeletionStatus: vi.fn(),
      recordFinalDecision: vi.fn().mockResolvedValue({
        human_review_id: "decision-1",
      }),
      requestDeletion: vi.fn().mockResolvedValue({
        deletion_request_id: "deletion-1",
        expected_targets: 4,
        manifest_id: "manifest-1",
        status: "requested",
        targets: [],
        verified_targets: 0,
      }),
    } as unknown as ReviewApi;
    render(<HumanReview api={api} />);

    fireEvent.change(screen.getByLabelText("초대 ID"), {
      target: { value: "invitation-1" },
    });
    fireEvent.change(screen.getByLabelText("결정 이유"), {
      target: { value: "사람 검토 결과 보류" },
    });
    fireEvent.click(screen.getByRole("button", { name: "보류 결정 기록" }));
    expect(
      await screen.findByText("사람 최종 결정이 기록되었습니다."),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("삭제 범위 ID"), {
      target: { value: "invitation-1" },
    });
    fireEvent.change(screen.getByLabelText("삭제 요청 이유"), {
      target: { value: "보관 목적 종료" },
    });
    fireEvent.click(screen.getByRole("button", { name: "삭제 요청" }));
    expect(await screen.findByText("삭제 상태: requested (0/4)")).toBeDefined();
  });
});
