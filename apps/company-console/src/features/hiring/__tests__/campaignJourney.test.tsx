import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { HiringApi } from "../api";
import { HiringJourney } from "../index";

describe("기업 채용 캠페인 여정", () => {
  it("실제 API gateway를 통해 직무, 기준, 캠페인과 초대를 구성한다", async () => {
    const api: HiringApi = {
      loadWorkspace: vi.fn().mockResolvedValue({
        user: {
          company_id: "company-1",
          company_user_id: "user-1",
          email: "owner@example.com",
          status: "active",
        },
        positions: [],
      }),
      createPosition: vi.fn().mockResolvedValue({
        position_id: "position-1",
        title: "백엔드 엔지니어",
        description: "분산 시스템 개발",
        status: "draft",
        row_version: 1,
        created_at: "2026-08-18T00:00:00Z",
      }),
      createAndPublishCriterion: vi.fn().mockResolvedValue({
        competency_model_version_id: "version-1",
        position_id: "position-1",
        version_number: 1,
        status: "published",
        row_version: 2,
        published_at: "2026-08-18T00:00:00Z",
        criteria: [],
        prohibited_topics: [],
        interview_duration_minutes: 30,
        persona_definition: {},
      }),
      createAndPublishCampaign: vi.fn().mockResolvedValue({
        campaign_id: "campaign-1",
        position_id: "position-1",
        competency_model_version_id: "version-1",
        name: "2026 백엔드 채용",
        candidate_instructions: "구체적인 경험을 설명해 주세요.",
        status: "published",
        row_version: 2,
        published_at: "2026-08-18T00:00:00Z",
      }),
      inviteApplicant: vi.fn().mockResolvedValue({
        accepted_count: 1,
        rejected_count: 0,
        invitations: [],
      }),
    };
    render(<HiringJourney api={api} onBearerChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("기업 Bearer 토큰"), {
      target: { value: "local-company-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "기업 API 연결" }));
    expect(await screen.findByText("owner@example.com 연결됨")).toBeDefined();

    fireEvent.change(screen.getByLabelText("직무명"), {
      target: { value: "백엔드 엔지니어" },
    });
    fireEvent.change(screen.getByLabelText("직무 설명"), {
      target: { value: "분산 시스템 개발" },
    });
    fireEvent.click(screen.getByRole("button", { name: "직무 저장" }));
    expect(
      await screen.findByText("직무가 API에 저장되었습니다."),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("평가 기준명"), {
      target: { value: "백엔드 설계" },
    });
    fireEvent.change(screen.getByLabelText("평가 기준 설명"), {
      target: { value: "시스템 설계 역량" },
    });
    fireEvent.click(screen.getByRole("button", { name: "평가 기준 게시" }));
    expect(
      await screen.findByText("평가 기준 버전 1이 게시되었습니다."),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("캠페인명"), {
      target: { value: "2026 백엔드 채용" },
    });
    fireEvent.click(screen.getByRole("button", { name: "캠페인 게시" }));
    expect(
      await screen.findByText("캠페인이 API에 게시되었습니다."),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("지원자 이름"), {
      target: { value: "지원자" },
    });
    fireEvent.change(screen.getByLabelText("지원자 이메일"), {
      target: { value: "applicant@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "초대 발송" }));
    expect(
      await screen.findByText("초대 1건이 API에서 접수되었습니다."),
    ).toBeDefined();

    await waitFor(() => expect(api.inviteApplicant).toHaveBeenCalledTimes(1));
  });
});
