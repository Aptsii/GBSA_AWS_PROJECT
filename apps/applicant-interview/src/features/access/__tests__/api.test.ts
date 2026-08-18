import type {
  ApplicantAccessState,
  ConsentView,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";
import { describe, expect, it, vi } from "vitest";

import { createApplicantAccessApi } from "../api";

describe("applicant access API", () => {
  it("exchanges the invitation then uses the scoped cookie for identity and consent", async () => {
    const state: ApplicantAccessState = {
      expires_at: "2026-08-19T00:00:00Z",
      invitation_id: "invitation-1",
      required_actions: ["consent"],
      state: "identity_verified",
    };
    const consent: ConsentView = {
      accepted_at: "2026-08-18T00:00:00Z",
      accepted_purposes: ["document_analysis", "recording", "ai_assessment"],
      consent_record_id: "consent-1",
      policy_version: "consent-ko-v1",
      retention_days: 180,
    };
    const post = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(state)
      .mockResolvedValueOnce(consent);
    const api = createApplicantAccessApi({
      post,
    } as unknown as BrowserApiClient);

    await api.exchangeInvitation("secure-token");
    await api.verifyIdentity("지원자", "applicant@example.com");
    await api.recordConsent();

    expect(post).toHaveBeenNthCalledWith(
      1,
      "/applicant/access/exchange",
      { invitation_token: "secure-token" },
      { auth: "none" },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      "/applicant/identity-verifications",
      { display_name: "지원자", verification_value: "applicant@example.com" },
      { auth: "applicant" },
    );
    expect(post).toHaveBeenNthCalledWith(
      3,
      "/applicant/consents",
      expect.objectContaining({
        accepted_purposes: ["document_analysis", "recording", "ai_assessment"],
        policy_version: "consent-ko-v1",
      }),
      { auth: "applicant" },
    );
  });
});
