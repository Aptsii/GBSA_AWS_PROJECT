import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ApplicantAccessApi } from "../api";
import { ApplicantAccessJourney } from "../index";

describe("지원자 접근 및 동의 여정", () => {
  it("API 쿠키 세션으로 초대 교환, 본인 확인과 동의를 완료한다", async () => {
    const onComplete = vi.fn();
    const api: ApplicantAccessApi = {
      exchangeInvitation: vi.fn().mockResolvedValue(undefined),
      verifyIdentity: vi.fn().mockResolvedValue({
        expires_at: "2026-08-19T00:00:00Z",
        invitation_id: "invitation-1",
        required_actions: ["consent"],
        state: "identity_verified",
      }),
      recordConsent: vi.fn().mockResolvedValue({
        accepted_at: "2026-08-18T00:00:00Z",
        accepted_purposes: ["document_analysis", "recording", "ai_assessment"],
        consent_record_id: "consent-1",
        policy_version: "consent-ko-v1",
        retention_days: 180,
      }),
    };
    render(<ApplicantAccessJourney api={api} onComplete={onComplete} />);

    fireEvent.change(screen.getByLabelText("초대 코드"), {
      target: { value: "secure-invitation-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "초대 확인" }));

    expect(await screen.findByLabelText("이름")).toBeDefined();
    fireEvent.change(screen.getByLabelText("이름"), {
      target: { value: "지원자" },
    });
    fireEvent.change(screen.getByLabelText("본인 확인 값"), {
      target: { value: "applicant@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "본인 확인" }));

    const submit = await screen.findByRole("button", { name: "동의하고 계속" });
    expect(submit).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByLabelText("문서 분석 동의"));
    fireEvent.click(screen.getByLabelText("면접 녹화 동의"));
    fireEvent.click(screen.getByLabelText("AI 평가 동의"));
    fireEvent.click(submit);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "동의가 API에 기록되었습니다.",
    );
    expect(onComplete).toHaveBeenCalledOnce();
    expect(api.recordConsent).toHaveBeenCalledOnce();
  });
});
