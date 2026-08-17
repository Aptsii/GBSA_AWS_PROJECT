import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EquipmentCheck } from "../EquipmentCheck";
import { InterviewRoom } from "../InterviewRoom";

describe("복구 가능한 면접 여정", () => {
  it("장비 점검 후 답변 완료와 text-only 상태를 안내한다", () => {
    const onReady = vi.fn();
    render(React.createElement(EquipmentCheck, { onReady }));
    fireEvent.click(screen.getByRole("button", { name: "장비 점검 완료" }));
    expect(onReady).toHaveBeenCalledOnce();

    const onCompleteAnswer = vi.fn();
    render(
      React.createElement(InterviewRoom, {
        question: "설계 이유를 설명해 주세요.",
        textOnly: true,
        onCompleteAnswer,
      }),
    );
    expect(screen.getByText("음성 없이 텍스트로 진행합니다.")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "답변 완료" }));
    expect(onCompleteAnswer).toHaveBeenCalledOnce();
  });
});
