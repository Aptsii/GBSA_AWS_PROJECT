import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SubmissionApi } from "../api";
import { SubmissionJourney } from "../index";

describe("지원 자료 제출 여정", () => {
  it("실제 API gateway로 저장소를 제출하고 부분 완료 영향을 표시한다", async () => {
    const api: SubmissionApi = {
      getReadiness: vi.fn().mockResolvedValue({
        interview_ready: true,
        overall_status: "partial",
        submissions: [
          {
            created_at: "2026-08-18T00:00:00Z",
            impact_summary:
              "PDF 한 페이지를 읽지 못했지만 면접 준비는 가능합니다.",
            source_type: "pdf",
            status: "partial",
            submission_id: "submission-1",
          },
        ],
        impact_summary: "일부 자료 분석이 제한되었습니다.",
        strategy_id: "strategy-1",
        strategy_version: 1,
      }),
      submitFile: vi.fn(),
      submitRepository: vi.fn().mockResolvedValue({
        created_at: "2026-08-18T00:00:00Z",
        source_type: "public_git",
        status: "received",
        submission_id: "submission-2",
      }),
    };
    render(<SubmissionJourney api={api} pollIntervalMs={0} />);

    expect(await screen.findByText("부분 완료")).toBeDefined();
    fireEvent.change(screen.getByLabelText("공개 저장소 주소"), {
      target: { value: "https://github.com/example/public-repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "저장소 제출" }));

    expect(
      await screen.findByText("저장소가 API에 접수되었습니다."),
    ).toBeDefined();
    expect(api.submitRepository).toHaveBeenCalledWith(
      "https://github.com/example/public-repo",
    );
    expect(screen.getByText(/PDF 한 페이지/)).toBeDefined();
  });

  it("파일을 선택하기 전에는 문서 제출을 비활성화한다", () => {
    const api: SubmissionApi = {
      getReadiness: vi.fn().mockResolvedValue({
        interview_ready: false,
        overall_status: "waiting",
        submissions: [],
      }),
      submitFile: vi.fn(),
      submitRepository: vi.fn(),
    };
    render(<SubmissionJourney api={api} pollIntervalMs={0} />);
    expect(screen.getByRole("button", { name: "문서 제출" })).toHaveProperty(
      "disabled",
      true,
    );
  });
});
