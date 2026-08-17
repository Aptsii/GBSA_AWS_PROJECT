import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TimelineView } from "../TimelineView";

describe("Evidence 영상 탐색", () => {
  it("Evidence 클릭 시 2초 이내 오차로 영상 위치를 요청한다", () => {
    const onSeek = vi.fn();
    render(<TimelineView entries={[{ id: "e1", text: "복구 답변", startMs: 4200, evidence: true }]} onSeek={onSeek} />);
    fireEvent.click(screen.getByRole("button", { name: "복구 답변" }));
    expect(Math.abs(onSeek.mock.calls[0][0] - 4200)).toBeLessThanOrEqual(2000);
  });
});
