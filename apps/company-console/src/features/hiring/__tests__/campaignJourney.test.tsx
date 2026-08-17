import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HiringJourney } from "../index";

describe("기업 채용 캠페인 여정", () => {
  it("직무, 평가 기준, 캠페인, 초대를 순서대로 구성한다", () => {
    render(<HiringJourney />);

    fireEvent.change(screen.getByLabelText("직무명"), {
      target: { value: "백엔드 엔지니어" },
    });
    fireEvent.click(screen.getByRole("button", { name: "직무 저장" }));
    expect(screen.getByText("직무가 저장되었습니다.")).toBeDefined();

    fireEvent.change(screen.getByLabelText("평가 기준명"), {
      target: { value: "백엔드 설계" },
    });
    fireEvent.click(screen.getByRole("button", { name: "평가 기준 게시" }));
    expect(
      screen.getByText("게시된 평가 기준은 수정할 수 없습니다."),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("캠페인명"), {
      target: { value: "2026 백엔드 채용" },
    });
    fireEvent.click(screen.getByRole("button", { name: "캠페인 게시" }));
    expect(
      screen.getByText("평가 기준 버전 1에 고정되었습니다."),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("지원자 이메일"), {
      target: { value: "candidate@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "초대 발송" }));
    expect(
      screen.getByText("초대 1건이 안전하게 발송 대기 중입니다."),
    ).toBeDefined();
  });
});
