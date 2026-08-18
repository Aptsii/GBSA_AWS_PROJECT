import type {
  Campaign,
  CompetencyModelVersion,
  CompanyUserView,
  InvitationBatchResult,
  Position,
  PositionPage,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";
import { describe, expect, it, vi } from "vitest";

import { createHiringApi } from "../api";

describe("hiring API", () => {
  it("uses the frozen company routes and optimistic publish headers", async () => {
    const user: CompanyUserView = {
      company_id: "company-1",
      company_user_id: "user-1",
      email: "owner@example.com",
      status: "active",
    };
    const position: Position = {
      position_id: "position-1",
      title: "백엔드 엔지니어",
      description: "분산 시스템 개발",
      status: "draft",
      row_version: 1,
      created_at: "2026-08-18T00:00:00Z",
    };
    const version: CompetencyModelVersion = {
      competency_model_version_id: "version-1",
      position_id: position.position_id,
      version_number: 1,
      status: "draft",
      row_version: 1,
      published_at: null,
      criteria: [],
      prohibited_topics: [],
      interview_duration_minutes: 30,
      persona_definition: {},
    };
    const publishedVersion = {
      ...version,
      status: "published" as const,
      row_version: 2,
    };
    const campaign: Campaign = {
      campaign_id: "campaign-1",
      position_id: position.position_id,
      competency_model_version_id: version.competency_model_version_id,
      name: "2026 백엔드 채용",
      candidate_instructions: "구체적인 경험을 설명해 주세요.",
      status: "draft",
      row_version: 1,
      published_at: null,
    };
    const publishedCampaign = {
      ...campaign,
      status: "published" as const,
      row_version: 2,
    };
    const invitationResult: InvitationBatchResult = {
      accepted_count: 1,
      rejected_count: 0,
      invitations: [],
    };
    const get = vi
      .fn()
      .mockResolvedValueOnce(user)
      .mockResolvedValueOnce({
        items: [position],
        next_cursor: null,
      } satisfies PositionPage);
    const post = vi
      .fn()
      .mockResolvedValueOnce(position)
      .mockResolvedValueOnce(version)
      .mockResolvedValueOnce(publishedVersion)
      .mockResolvedValueOnce(campaign)
      .mockResolvedValueOnce(publishedCampaign)
      .mockResolvedValueOnce(invitationResult);
    const api = createHiringApi({ get, post } as unknown as BrowserApiClient);

    await expect(api.loadWorkspace()).resolves.toEqual({
      user,
      positions: [position],
    });
    await api.createPosition({
      title: position.title,
      description: position.description,
    });
    await api.createAndPublishCriterion(position.position_id, {
      name: "백엔드 설계",
      description: "시스템 설계 역량",
      prohibitedTopics: ["가족관계"],
    });
    await api.createAndPublishCampaign(
      position.position_id,
      version.competency_model_version_id,
      {
        name: campaign.name,
        candidateInstructions: campaign.candidate_instructions,
      },
    );
    await api.inviteApplicant(campaign.campaign_id, {
      displayName: "지원자",
      email: "applicant@example.com",
      expiresAt: "2026-08-25T00:00:00Z",
    });

    expect(get).toHaveBeenNthCalledWith(1, "/me", { auth: "company" });
    expect(get).toHaveBeenNthCalledWith(2, "/positions?limit=100", {
      auth: "company",
    });
    expect(post).toHaveBeenCalledWith(
      "/competency-model-versions/version-1/publish",
      undefined,
      expect.objectContaining({ headers: { "If-Match-Version": "1" } }),
    );
    expect(post).toHaveBeenCalledWith(
      "/campaigns/campaign-1/publish",
      undefined,
      expect.objectContaining({ headers: { "If-Match-Version": "1" } }),
    );
  });
});
