import { ApiProblem } from "@interview-evidence/web-client";
import { FormEvent, useState } from "react";

import { applicantAccessApi, type ApplicantAccessApi } from "./api";

interface ApplicantAccessJourneyProps {
  readonly api?: ApplicantAccessApi;
  readonly onComplete?: () => void;
}

export function ApplicantAccessJourney({
  api = applicantAccessApi,
  onComplete,
}: ApplicantAccessJourneyProps) {
  const [step, setStep] = useState<"token" | "identity" | "consent" | "done">(
    "token",
  );
  const [invitationToken, setInvitationToken] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [verificationValue, setVerificationValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retentionDays, setRetentionDays] = useState<number | null>(null);
  const [purposes, setPurposes] = useState({
    documentAnalysis: false,
    recording: false,
    aiAssessment: false,
  });

  const allPurposesAccepted = Object.values(purposes).every(Boolean);

  async function submit(
    event: FormEvent<HTMLFormElement>,
    operation: () => Promise<void>,
  ) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await operation();
    } catch (caught) {
      setError(problemMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="applicant-access-title">
      <p>안전한 지원자 접근</p>
      <h1 id="applicant-access-title">면접 시작 전 확인</h1>
      <p>
        초대 교환 후 발급되는 보안 쿠키는 현재 지원자의 API 요청에만 사용됩니다.
      </p>
      {error && <p role="alert">{error}</p>}

      {step === "token" && (
        <form
          onSubmit={(event) =>
            void submit(event, async () => {
              await api.exchangeInvitation(invitationToken);
              setStep("identity");
            })
          }
        >
          <label htmlFor="invitation-token">초대 코드</label>
          <input
            id="invitation-token"
            value={invitationToken}
            onChange={(event) => setInvitationToken(event.target.value)}
            autoComplete="one-time-code"
            required
          />
          <button type="submit" disabled={!invitationToken.trim() || busy}>
            {busy ? "확인 중" : "초대 확인"}
          </button>
        </form>
      )}

      {step === "identity" && (
        <form
          onSubmit={(event) =>
            void submit(event, async () => {
              await api.verifyIdentity(displayName, verificationValue);
              setStep("consent");
            })
          }
        >
          <label htmlFor="display-name">이름</label>
          <input
            id="display-name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            autoComplete="name"
            required
          />
          <label htmlFor="verification-value">본인 확인 값</label>
          <input
            id="verification-value"
            value={verificationValue}
            onChange={(event) => setVerificationValue(event.target.value)}
            autoComplete="email"
            required
          />
          <button
            type="submit"
            disabled={!displayName.trim() || !verificationValue.trim() || busy}
          >
            {busy ? "확인 중" : "본인 확인"}
          </button>
        </form>
      )}

      {step === "consent" && (
        <form
          onSubmit={(event) =>
            void submit(event, async () => {
              const consent = await api.recordConsent();
              setRetentionDays(consent.retention_days);
              setStep("done");
              onComplete?.();
            })
          }
        >
          <p>동의하지 않으면 분석, 녹화, AI 평가는 시작되지 않습니다.</p>
          <label>
            <input
              type="checkbox"
              checked={purposes.documentAnalysis}
              onChange={(event) =>
                setPurposes((current) => ({
                  ...current,
                  documentAnalysis: event.target.checked,
                }))
              }
            />
            문서 분석 동의
          </label>
          <label>
            <input
              type="checkbox"
              checked={purposes.recording}
              onChange={(event) =>
                setPurposes((current) => ({
                  ...current,
                  recording: event.target.checked,
                }))
              }
            />
            면접 녹화 동의
          </label>
          <label>
            <input
              type="checkbox"
              checked={purposes.aiAssessment}
              onChange={(event) =>
                setPurposes((current) => ({
                  ...current,
                  aiAssessment: event.target.checked,
                }))
              }
            />
            AI 평가 동의
          </label>
          <button type="submit" disabled={!allPurposesAccepted || busy}>
            {busy ? "기록 중" : "동의하고 계속"}
          </button>
        </form>
      )}

      {step === "done" && (
        <p role="status">
          동의가 API에 기록되었습니다.
          {retentionDays !== null
            ? ` 보관 기간은 ${retentionDays}일입니다.`
            : ""}
        </p>
      )}
    </section>
  );
}

export default ApplicantAccessJourney;

function problemMessage(caught: unknown): string {
  if (caught instanceof ApiProblem) {
    return caught.detail
      ? `${caught.message}: ${caught.detail}`
      : caught.message;
  }
  return "지원자 접근 API 요청 중 오류가 발생했습니다.";
}
