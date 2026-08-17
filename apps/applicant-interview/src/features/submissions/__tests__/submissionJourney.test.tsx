import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SubmissionJourney } from "../index";

describe("지원 자료 제출 여정", () => {
  it("문서와 공개 저장소를 제출하고 부분 완료 영향을 표시한다", () => {
    const onSubmit = vi.fn();
    render(
      <SubmissionJourney
        onSubmit={onSubmit}
        initialSubmissions={[
          {
            id: "submission-1",
            label: "portfolio.pdf",
            status: "partial",
            impactSummary: "PDF 한 페이지를 읽지 못했지만 면접 준비는 가능합니다.",
          },
        ]}
      />,
    );

    fireEvent.change(screen.getByLabelText("공개 저장소 주소"), {
      target: { value: "https://github.com/example/public-repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "저장소 제출" }));

    expect(onSubmit).toHaveBeenCalledWith({
      sourceType: "public_git",
      publicUrl: "https://github.com/example/public-repo",
    });
    expect(screen.getByText("부분 완료")).toBeDefined();
    expect(screen.getByText(/PDF 한 페이지/)).toBeDefined();
  });

  it("파일을 선택하기 전에는 문서 제출을 비활성화한다", () => {
    render(<SubmissionJourney />);
    expect(screen.getByRole("button", { name: "문서 제출" })).toHaveProperty(
      "disabled",
      true,
    );
  });
});
