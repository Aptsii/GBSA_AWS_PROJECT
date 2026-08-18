import type {
  ApplicantAccessState,
  ApplicantIdentityVerification,
  ApplicantTokenExchange,
  ConsentCreate,
  ConsentView,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";

import { apiClient } from "../../app/api";

const CONSENT_CONTENT_DIGEST =
  "7ef1cb257e0268838502a9c8b06224d2cc5e38f1ba20c34d4853cd4e891c4ca2";

export interface ApplicantAccessApi {
  exchangeInvitation(invitationToken: string): Promise<void>;
  verifyIdentity(
    displayName: string,
    verificationValue: string,
  ): Promise<ApplicantAccessState>;
  recordConsent(): Promise<ConsentView>;
}

export function createApplicantAccessApi(
  client: BrowserApiClient,
): ApplicantAccessApi {
  return {
    exchangeInvitation(invitationToken) {
      const payload: ApplicantTokenExchange = {
        invitation_token: invitationToken,
      };
      return client.post<void, ApplicantTokenExchange>(
        "/applicant/access/exchange",
        payload,
        {
          auth: "none",
        },
      );
    },
    verifyIdentity(displayName, verificationValue) {
      const payload: ApplicantIdentityVerification = {
        display_name: displayName,
        verification_value: verificationValue,
      };
      return client.post<ApplicantAccessState, ApplicantIdentityVerification>(
        "/applicant/identity-verifications",
        payload,
        { auth: "applicant" },
      );
    },
    recordConsent() {
      const payload: ConsentCreate = {
        accepted_purposes: ["document_analysis", "recording", "ai_assessment"],
        consent_content_digest: CONSENT_CONTENT_DIGEST,
        policy_version: "consent-ko-v1",
      };
      return client.post<ConsentView, ConsentCreate>(
        "/applicant/consents",
        payload,
        {
          auth: "applicant",
        },
      );
    },
  };
}

export const applicantAccessApi = createApplicantAccessApi(apiClient);
