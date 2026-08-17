import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
});
