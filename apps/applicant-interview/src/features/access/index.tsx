import { FormEvent, useState } from "react";

interface ApplicantAccessJourneyProps {
  readonly onComplete?: () => void;
}

export function ApplicantAccessJourney({
  onComplete,
}: ApplicantAccessJourneyProps) {
  const [step, setStep] = useState<"token" | "identity" | "consent" | "done">(
    "token",
  );
  const [invitationToken, setInvitationToken] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [purposes, setPurposes] = useState({
    documentAnalysis: false,
    recording: false,
    aiAssessment: false,
  });

  function submit(event: FormEvent<HTMLFormElement>, nextStep: typeof step) {
    event.preventDefault();
    setStep(nextStep);
  }

  const allPurposesAccepted = Object.values(purposes).every(Boolean);

  return (
    <section aria-labelledby="applicant-access-title">
      <p>안전한 지원자 접근</p>
      <h1 id="applicant-access-title">면접 시작 전 확인</h1>

      {step === "token" && (
        <form onSubmit={(event) => submit(event, "identity")}>
          <label htmlFor="invitation-token">초대 코드</label>
          <input
            id="invitation-token"
            value={invitationToken}
            onChange={(event) => setInvitationToken(event.target.value)}
            autoComplete="one-time-code"
            required
          />
          <button type="submit" disabled={!invitationToken.trim()}>
            초대 확인
          </button>
        </form>
      )}

      {step === "identity" && (
        <form onSubmit={(event) => submit(event, "consent")}>
          <label htmlFor="display-name">이름</label>
          <input
            id="display-name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            autoComplete="name"
            required
          />
          <button type="submit" disabled={!displayName.trim()}>
            본인 확인
          </button>
        </form>
      )}

      {step === "consent" && (
        <form
          onSubmit={(event) => {
            submit(event, "done");
            onComplete?.();
          }}
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
          <button type="submit" disabled={!allPurposesAccepted}>
            동의하고 계속
          </button>
        </form>
      )}

      {step === "done" && <p role="status">동의가 기록되었습니다.</p>}
    </section>
  );
}

export default ApplicantAccessJourney;
