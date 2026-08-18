import type {
  Campaign,
  CompetencyModelVersion,
  CompanyUserView,
  Position,
} from "@interview-evidence/contracts";
import { ApiProblem } from "@interview-evidence/web-client";
import { FormEvent, useEffect, useState } from "react";

import { companyIdentitySession } from "../../app/api";
import type { CompanyIdentitySession } from "../company/identity";
import { hiringApi, type HiringApi } from "./api";

interface HiringJourneyProps {
  readonly api?: HiringApi;
  readonly identity?: CompanyIdentitySession;
}

export function HiringJourney({
  api = hiringApi,
  identity = companyIdentitySession,
}: HiringJourneyProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<CompanyUserView | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [criterionVersion, setCriterionVersion] =
    useState<CompetencyModelVersion | null>(null);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [restoreOnMount] = useState(() => identity.hasSession());
  const [busy, setBusy] = useState<string | null>(() =>
    restoreOnMount ? "restore" : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [positionName, setPositionName] = useState("");
  const [positionDescription, setPositionDescription] = useState("");
  const [criterionName, setCriterionName] = useState("");
  const [criterionDescription, setCriterionDescription] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [candidateInstructions, setCandidateInstructions] = useState(
    "구체적인 경험과 본인이 맡은 역할을 중심으로 답변해 주세요.",
  );
  const [applicantName, setApplicantName] = useState("");
  const [applicantEmail, setApplicantEmail] = useState("");

  useEffect(() => {
    if (!restoreOnMount) return;
    let active = true;
    void api
      .loadWorkspace()
      .then((workspace) => {
        if (!active) return;
        setUser(workspace.user);
        setPosition(workspace.positions[0] ?? null);
        setStatus(`${workspace.user.email} 세션 복원됨`);
      })
      .catch(() => {
        identity.signOut();
      })
      .finally(() => {
        if (active) setBusy(null);
      });
    return () => {
      active = false;
    };
  }, [api, identity, restoreOnMount]);

  async function run(action: string, operation: () => Promise<void>) {
    setBusy(action);
    setError(null);
    setStatus(null);
    try {
      await operation();
    } catch (caught) {
      setError(problemMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  function submit(
    event: FormEvent<HTMLFormElement>,
    action: string,
    operation: () => Promise<void>,
  ) {
    event.preventDefault();
    void run(action, operation);
  }

  return (
    <section aria-labelledby="hiring-journey-title">
      <p>Lane A · 기업 채용 설정</p>
      <h1 id="hiring-journey-title">채용 캠페인 만들기</h1>
      <p>
        각 단계는 실제 API에 저장되며 앞 단계가 완료되어야 다음 단계가
        활성화됩니다.
      </p>

      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}

      <form
        onSubmit={(event) =>
          submit(event, "login", async () => {
            await identity.signIn(email, password);
            const workspace = await api.loadWorkspace();
            setUser(workspace.user);
            setPosition(workspace.positions[0] ?? null);
            setPassword("");
            setStatus(`${workspace.user.email} 연결됨`);
          })
        }
      >
        <h2>0. 기업 로그인</h2>
        <label htmlFor="company-email">기업 이메일</label>
        <input
          id="company-email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <label htmlFor="company-password">비밀번호</label>
        <input
          id="company-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <button
          type="submit"
          disabled={!email.includes("@") || !password || busy !== null}
        >
          {busy === "login" ? "로그인 중" : "로그인"}
        </button>
        {user && (
          <p>
            연결 계정: {user.email}{" "}
            <button
              type="button"
              onClick={() => {
                identity.signOut();
                setUser(null);
                setPosition(null);
                setCriterionVersion(null);
                setCampaign(null);
                setStatus("로그아웃되었습니다.");
              }}
            >
              로그아웃
            </button>
          </p>
        )}
      </form>

      <form
        onSubmit={(event) =>
          submit(event, "position", async () => {
            const created = await api.createPosition({
              description: positionDescription,
              title: positionName,
            });
            setPosition(created);
            setStatus("직무가 API에 저장되었습니다.");
          })
        }
      >
        <h2>1. 직무</h2>
        <label htmlFor="position-name">직무명</label>
        <input
          id="position-name"
          value={positionName}
          onChange={(event) => setPositionName(event.target.value)}
          required
        />
        <label htmlFor="position-description">직무 설명</label>
        <textarea
          id="position-description"
          value={positionDescription}
          onChange={(event) => setPositionDescription(event.target.value)}
          required
        />
        <button
          type="submit"
          disabled={
            !user ||
            !positionName.trim() ||
            !positionDescription.trim() ||
            busy !== null
          }
        >
          {busy === "position" ? "저장 중" : "직무 저장"}
        </button>
      </form>

      <form
        onSubmit={(event) =>
          submit(event, "criterion", async () => {
            if (!position) return;
            const published = await api.createAndPublishCriterion(
              position.position_id,
              {
                description: criterionDescription,
                name: criterionName,
                prohibitedTopics: ["가족관계", "출신 지역", "연령 추정"],
              },
            );
            setCriterionVersion(published);
            setStatus(
              `평가 기준 버전 ${published.version_number}이 게시되었습니다.`,
            );
          })
        }
      >
        <h2>2. 평가 기준 버전</h2>
        <label htmlFor="criterion-name">평가 기준명</label>
        <input
          id="criterion-name"
          value={criterionName}
          onChange={(event) => setCriterionName(event.target.value)}
          required
        />
        <label htmlFor="criterion-description">평가 기준 설명</label>
        <textarea
          id="criterion-description"
          value={criterionDescription}
          onChange={(event) => setCriterionDescription(event.target.value)}
          required
        />
        <button
          type="submit"
          disabled={
            !position ||
            !criterionName.trim() ||
            !criterionDescription.trim() ||
            busy !== null
          }
        >
          {busy === "criterion" ? "게시 중" : "평가 기준 게시"}
        </button>
      </form>

      <form
        onSubmit={(event) =>
          submit(event, "campaign", async () => {
            if (!position || !criterionVersion) return;
            const published = await api.createAndPublishCampaign(
              position.position_id,
              criterionVersion.competency_model_version_id,
              { candidateInstructions, name: campaignName },
            );
            setCampaign(published);
            setStatus("캠페인이 API에 게시되었습니다.");
          })
        }
      >
        <h2>3. 캠페인</h2>
        <label htmlFor="campaign-name">캠페인명</label>
        <input
          id="campaign-name"
          value={campaignName}
          onChange={(event) => setCampaignName(event.target.value)}
          required
        />
        <label htmlFor="candidate-instructions">지원자 안내</label>
        <textarea
          id="candidate-instructions"
          value={candidateInstructions}
          onChange={(event) => setCandidateInstructions(event.target.value)}
          required
        />
        <button
          type="submit"
          disabled={!criterionVersion || !campaignName.trim() || busy !== null}
        >
          {busy === "campaign" ? "게시 중" : "캠페인 게시"}
        </button>
      </form>

      <form
        onSubmit={(event) =>
          submit(event, "invitation", async () => {
            if (!campaign) return;
            const result = await api.inviteApplicant(campaign.campaign_id, {
              displayName: applicantName,
              email: applicantEmail,
              expiresAt: invitationExpiry(),
            });
            setStatus(
              `초대 ${result.accepted_count}건이 API에서 접수되었습니다.`,
            );
          })
        }
      >
        <h2>4. 지원자 초대</h2>
        <label htmlFor="applicant-name">지원자 이름</label>
        <input
          id="applicant-name"
          value={applicantName}
          onChange={(event) => setApplicantName(event.target.value)}
          required
        />
        <label htmlFor="applicant-email">지원자 이메일</label>
        <input
          id="applicant-email"
          type="email"
          value={applicantEmail}
          onChange={(event) => setApplicantEmail(event.target.value)}
          required
        />
        <button
          type="submit"
          disabled={
            !campaign ||
            !applicantName.trim() ||
            !applicantEmail.includes("@") ||
            busy !== null
          }
        >
          {busy === "invitation" ? "접수 중" : "초대 발송"}
        </button>
      </form>
    </section>
  );
}

export default HiringJourney;

function invitationExpiry(): string {
  return new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
}

function problemMessage(caught: unknown): string {
  if (caught instanceof ApiProblem) {
    return caught.detail
      ? `${caught.message}: ${caught.detail}`
      : caught.message;
  }
  if (caught instanceof Error) return caught.message;
  return "API 요청 중 예상하지 못한 오류가 발생했습니다.";
}
