import { FormEvent, useState } from "react";

export function HiringJourney() {
  const [positionName, setPositionName] = useState("");
  const [criterionName, setCriterionName] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [applicantEmail, setApplicantEmail] = useState("");
  const [positionSaved, setPositionSaved] = useState(false);
  const [criterionPublished, setCriterionPublished] = useState(false);
  const [campaignPublished, setCampaignPublished] = useState(false);
  const [invitationQueued, setInvitationQueued] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>, action: () => void) {
    event.preventDefault();
    action();
  }

  return (
    <section aria-labelledby="hiring-journey-title">
      <p>Lane A · 기업 채용 설정</p>
      <h1 id="hiring-journey-title">채용 캠페인 만들기</h1>

      <form onSubmit={(event) => submit(event, () => setPositionSaved(true))}>
        <h2>1. 직무</h2>
        <label htmlFor="position-name">직무명</label>
        <input
          id="position-name"
          value={positionName}
          onChange={(event) => setPositionName(event.target.value)}
          required
        />
        <button type="submit" disabled={!positionName.trim()}>
          직무 저장
        </button>
        {positionSaved && <p role="status">직무가 저장되었습니다.</p>}
      </form>

      <form
        onSubmit={(event) => submit(event, () => setCriterionPublished(true))}
      >
        <h2>2. 평가 기준 버전</h2>
        <label htmlFor="criterion-name">평가 기준명</label>
        <input
          id="criterion-name"
          value={criterionName}
          onChange={(event) => setCriterionName(event.target.value)}
          disabled={criterionPublished}
          required
        />
        <button
          type="submit"
          disabled={
            !positionSaved || !criterionName.trim() || criterionPublished
          }
        >
          평가 기준 게시
        </button>
        {criterionPublished && (
          <p role="status">게시된 평가 기준은 수정할 수 없습니다.</p>
        )}
      </form>

      <form
        onSubmit={(event) => submit(event, () => setCampaignPublished(true))}
      >
        <h2>3. 캠페인</h2>
        <label htmlFor="campaign-name">캠페인명</label>
        <input
          id="campaign-name"
          value={campaignName}
          onChange={(event) => setCampaignName(event.target.value)}
          required
        />
        <button
          type="submit"
          disabled={!criterionPublished || !campaignName.trim()}
        >
          캠페인 게시
        </button>
        {campaignPublished && (
          <p role="status">평가 기준 버전 1에 고정되었습니다.</p>
        )}
      </form>

      <form
        onSubmit={(event) => submit(event, () => setInvitationQueued(true))}
      >
        <h2>4. 지원자 초대</h2>
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
          disabled={!campaignPublished || !applicantEmail.includes("@")}
        >
          초대 발송
        </button>
        {invitationQueued && (
          <p role="status">초대 1건이 안전하게 발송 대기 중입니다.</p>
        )}
      </form>
    </section>
  );
}

export default HiringJourney;
