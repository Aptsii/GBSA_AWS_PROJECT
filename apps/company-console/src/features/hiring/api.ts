import type {
  Campaign,
  CampaignCreate,
  CompetencyModelVersion,
  CompetencyModelVersionCreate,
  CompanyUserView,
  InvitationBatchCreate,
  InvitationBatchResult,
  Position,
  PositionCreate,
  PositionPage,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";

import { apiClient } from "../../app/api";

export interface CriterionDraft {
  readonly name: string;
  readonly description: string;
  readonly prohibitedTopics: readonly string[];
}

export interface CampaignDraft {
  readonly name: string;
  readonly candidateInstructions: string;
}

export interface ApplicantInvitationDraft {
  readonly displayName: string;
  readonly email: string;
  readonly expiresAt: string;
}

export interface HiringApi {
  loadWorkspace(): Promise<{
    readonly user: CompanyUserView;
    readonly positions: readonly Position[];
  }>;
  createPosition(payload: PositionCreate): Promise<Position>;
  createAndPublishCriterion(
    positionId: string,
    draft: CriterionDraft,
  ): Promise<CompetencyModelVersion>;
  createAndPublishCampaign(
    positionId: string,
    competencyModelVersionId: string,
    draft: CampaignDraft,
  ): Promise<Campaign>;
  inviteApplicant(
    campaignId: string,
    draft: ApplicantInvitationDraft,
  ): Promise<InvitationBatchResult>;
}

export function createHiringApi(client: BrowserApiClient): HiringApi {
  return {
    async loadWorkspace() {
      const [user, page] = await Promise.all([
        client.get<CompanyUserView>("/me", { auth: "company" }),
        client.get<PositionPage>("/positions?limit=100", { auth: "company" }),
      ]);
      return { user, positions: page.items };
    },
    createPosition(payload) {
      return client.post<Position, PositionCreate>("/positions", payload, {
        auth: "company",
      });
    },
    async createAndPublishCriterion(positionId, draft) {
      const code = criterionCode(draft.name);
      const payload: CompetencyModelVersionCreate = {
        criteria: [
          {
            abstain_guidance: "답변 근거가 부족하면 판단을 유보합니다.",
            code,
            common_questions: [
              "관련 경험에서 맡은 역할과 결과를 설명해 주세요.",
            ],
            description: draft.description,
            good_evidence: { guidance: "역할, 선택, 결과가 구체적인 답변" },
            name: draft.name,
            required: true,
            weak_evidence: { guidance: "역할이나 결과가 불명확한 답변" },
            weight: 1,
          },
        ],
        interview_duration_minutes: 30,
        persona_definition: {
          name: "하루",
          tone: "차분하고 명확한 한국어",
          voice: "Seoyeon",
        },
        prohibited_topics: [...draft.prohibitedTopics],
      };
      const created = await client.post<
        CompetencyModelVersion,
        CompetencyModelVersionCreate
      >(`/positions/${positionId}/competency-model-versions`, payload, {
        auth: "company",
      });
      return client.post<CompetencyModelVersion, undefined>(
        `/competency-model-versions/${created.competency_model_version_id}/publish`,
        undefined,
        {
          auth: "company",
          headers: { "If-Match-Version": String(created.row_version) },
        },
      );
    },
    async createAndPublishCampaign(
      positionId,
      competencyModelVersionId,
      draft,
    ) {
      const payload: CampaignCreate = {
        candidate_instructions: draft.candidateInstructions,
        competency_model_version_id: competencyModelVersionId,
        name: draft.name,
        position_id: positionId,
      };
      const created = await client.post<Campaign, CampaignCreate>(
        "/campaigns",
        payload,
        {
          auth: "company",
        },
      );
      return client.post<Campaign, undefined>(
        `/campaigns/${created.campaign_id}/publish`,
        undefined,
        {
          auth: "company",
          headers: { "If-Match-Version": String(created.row_version) },
        },
      );
    },
    inviteApplicant(campaignId, draft) {
      const payload: InvitationBatchCreate = {
        applicants: [{ display_name: draft.displayName, email: draft.email }],
        expires_at: draft.expiresAt,
      };
      return client.post<InvitationBatchResult, InvitationBatchCreate>(
        `/campaigns/${campaignId}/invitations`,
        payload,
        { auth: "company" },
      );
    },
  };
}

export const hiringApi = createHiringApi(apiClient);

function criterionCode(name: string): string {
  const normalized = name
    .normalize("NFKD")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
  return normalized || "PRIMARY_COMPETENCY";
}
