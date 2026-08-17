import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApplicantAccessJourney } from "../index";

describe("지원자 접근 및 동의 여정", () => {
  it("초대 교환, 본인 확인, 필수 동의를 순서대로 완료한다", () => {
    const onComplete = vi.fn();
    render(<ApplicantAccessJourney onComplete={onComplete} />);

    fireEvent.change(screen.getByLabelText("초대 코드"), {
      target: { value: "secure-invitation-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "초대 확인" }));

    fireEvent.change(screen.getByLabelText("이름"), {
      target: { value: "지원자" },
    });
    fireEvent.click(screen.getByRole("button", { name: "본인 확인" }));

    const submit = screen.getByRole("button", { name: "동의하고 계속" });
    expect(submit).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByLabelText("문서 분석 동의"));
    fireEvent.click(screen.getByLabelText("면접 녹화 동의"));
    fireEvent.click(screen.getByLabelText("AI 평가 동의"));
    expect(submit).toHaveProperty("disabled", false);
    fireEvent.click(submit);

    expect(onComplete).toHaveBeenCalledOnce();
    expect(screen.getByText("동의가 기록되었습니다.")).toBeDefined();
  });
});
