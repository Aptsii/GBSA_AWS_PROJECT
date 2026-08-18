import type {
  DeletionStatus,
  FinalDecisionCreate,
} from "@interview-evidence/contracts";
import { useState } from "react";

import { reviewApi, type ReviewApi } from "./api";

interface HumanReviewProps {
  readonly api?: ReviewApi;
  readonly onDecision?: (
    decision: "advance" | "reject" | "hold" | "withdrawn",
  ) => void;
  readonly deletionStatus?: string;
}

export function HumanReview({
  api = reviewApi,
  onDecision,
  deletionStatus: initialDeletionStatus = "요청 없음",
}: HumanReviewProps) {
  const [sessionId, setSessionId] = useState("");
  const [invitationId, setInvitationId] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [artifactType, setArtifactType] = useState<"note" | "bookmark">("note");
  const [artifactTargetId, setArtifactTargetId] = useState("");
  const [artifactValue, setArtifactValue] = useState("");
  const [deletionScopeType, setDeletionScopeType] = useState<
    "invitation" | "applicant"
  >("invitation");
  const [deletionScopeId, setDeletionScopeId] = useState("");
  const [deletionReason, setDeletionReason] = useState("");
  const [deletion, setDeletion] = useState<DeletionStatus | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function recordDecision(decision: FinalDecisionCreate["decision"]) {
    onDecision?.(decision);
    if (!invitationId.trim() || !decisionReason.trim()) return;
    await run(async () => {
      await api.recordFinalDecision(invitationId.trim(), {
        decision,
        reason: decisionReason.trim(),
      });
      setStatus("사람 최종 결정이 기록되었습니다.");
    });
  }

  async function createArtifact() {
    if (!sessionId.trim() || !artifactTargetId.trim() || !artifactValue.trim())
      return;
    await run(async () => {
      await api.createReviewArtifact(sessionId.trim(), {
        review_type: artifactType,
        target_id: artifactTargetId.trim(),
        value: artifactValue.trim(),
      });
      setStatus(
        `${artifactType === "note" ? "메모" : "북마크"}가 추가되었습니다.`,
      );
    });
  }

  async function requestDeletion() {
    if (!deletionScopeId.trim() || !deletionReason.trim()) return;
    await run(async () => {
      const result = await api.requestDeletion({
        scope_id: deletionScopeId.trim(),
        scope_type: deletionScopeType,
        reason: deletionReason.trim(),
      });
      setDeletion(result);
      setStatus("삭제 요청이 접수되었습니다.");
    });
  }

  async function refreshDeletion() {
    if (!deletion) return;
    await run(async () => {
      setDeletion(await api.getDeletionStatus(deletion.deletion_request_id));
      setStatus("삭제 검증 상태를 갱신했습니다.");
    });
  }

  async function run(operation: () => Promise<void>) {
    setBusy(true);
    setStatus("");
    setError("");
    try {
      await operation();
    } catch {
      setError("사람 검토 작업을 처리하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  const deletionLabel = deletion
    ? `${deletion.status} (${deletion.verified_targets}/${deletion.expected_targets})`
    : initialDeletionStatus;

  return (
    <section aria-labelledby="human-review-title">
      <h2 id="human-review-title">사람 검토 기록</h2>
      <p>최종 결정은 회사 담당자만 기록할 수 있습니다.</p>
      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}

      <fieldset>
        <legend>메모 및 북마크</legend>
        <label htmlFor="review-session-id">면접 세션 ID</label>
        <input
          id="review-session-id"
          value={sessionId}
          onChange={(event) => setSessionId(event.target.value)}
        />
        <label htmlFor="artifact-type">기록 유형</label>
        <select
          id="artifact-type"
          value={artifactType}
          onChange={(event) =>
            setArtifactType(event.target.value as "note" | "bookmark")
          }
        >
          <option value="note">메모</option>
          <option value="bookmark">북마크</option>
        </select>
        <label htmlFor="artifact-target-id">대상 ID</label>
        <input
          id="artifact-target-id"
          value={artifactTargetId}
          onChange={(event) => setArtifactTargetId(event.target.value)}
        />
        <label htmlFor="artifact-value">기록 내용</label>
        <textarea
          id="artifact-value"
          value={artifactValue}
          onChange={(event) => setArtifactValue(event.target.value)}
        />
        <button
          type="button"
          onClick={() => void createArtifact()}
          disabled={busy}
        >
          검토 기록 추가
        </button>
      </fieldset>

      <fieldset>
        <legend>사람 최종 결정</legend>
        <label htmlFor="decision-invitation-id">초대 ID</label>
        <input
          id="decision-invitation-id"
          value={invitationId}
          onChange={(event) => setInvitationId(event.target.value)}
        />
        <label htmlFor="decision-reason">결정 이유</label>
        <textarea
          id="decision-reason"
          value={decisionReason}
          onChange={(event) => setDecisionReason(event.target.value)}
        />
        <button
          type="button"
          onClick={() => void recordDecision("hold")}
          disabled={busy}
        >
          보류 결정 기록
        </button>
        <button
          type="button"
          onClick={() => void recordDecision("advance")}
          disabled={busy}
        >
          다음 단계 결정 기록
        </button>
        <button
          type="button"
          onClick={() => void recordDecision("reject")}
          disabled={busy}
        >
          탈락 결정 기록
        </button>
        <button
          type="button"
          onClick={() => void recordDecision("withdrawn")}
          disabled={busy}
        >
          지원 철회 기록
        </button>
      </fieldset>

      <fieldset>
        <legend>개인정보 삭제</legend>
        <label htmlFor="deletion-scope-type">삭제 범위</label>
        <select
          id="deletion-scope-type"
          value={deletionScopeType}
          onChange={(event) =>
            setDeletionScopeType(
              event.target.value as "invitation" | "applicant",
            )
          }
        >
          <option value="invitation">초대</option>
          <option value="applicant">지원자</option>
        </select>
        <label htmlFor="deletion-scope-id">삭제 범위 ID</label>
        <input
          id="deletion-scope-id"
          value={deletionScopeId}
          onChange={(event) => setDeletionScopeId(event.target.value)}
        />
        <label htmlFor="deletion-reason">삭제 요청 이유</label>
        <textarea
          id="deletion-reason"
          value={deletionReason}
          onChange={(event) => setDeletionReason(event.target.value)}
        />
        <button
          type="button"
          onClick={() => void requestDeletion()}
          disabled={busy}
        >
          삭제 요청
        </button>
        <button
          type="button"
          onClick={() => void refreshDeletion()}
          disabled={busy || deletion === null}
        >
          삭제 상태 갱신
        </button>
        <p>삭제 상태: {deletionLabel}</p>
      </fieldset>
    </section>
  );
}
