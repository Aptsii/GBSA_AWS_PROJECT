import type {
  AssessmentState,
  ReportView as ReportContract,
} from "@interview-evidence/contracts";
import { useState } from "react";

import { reviewApi, type ReviewApi } from "./api";

export interface ReportItemSummary {
  readonly id: string;
  readonly criterion: string;
  readonly state: AssessmentState;
  readonly observation?: string;
  readonly rationale?: string;
  readonly uncertainty?: string;
}

interface ReportViewProps {
  readonly api?: ReviewApi;
  readonly initialSessionId?: string;
  readonly summary?: string;
  readonly items?: readonly ReportItemSummary[];
}

const labels: Record<AssessmentState, string> = {
  confirmed: "확인됨",
  partially_confirmed: "부분 확인",
  insufficient_evidence: "근거 부족",
  needs_follow_up: "추가 확인 필요",
};

export function ReportView({
  api = reviewApi,
  initialSessionId = "",
  summary:
    initialSummary = "면접이 완료되면 평가 기준별 Evidence가 여기에 표시됩니다.",
  items: initialItems = [],
}: ReportViewProps) {
  const [sessionId, setSessionId] = useState(initialSessionId);
  const [report, setReport] = useState<ReportContract | null>(null);
  const [processingMessage, setProcessingMessage] = useState("");
  const [reviewReasons, setReviewReasons] = useState<Record<string, string>>(
    {},
  );
  const [reviewStates, setReviewStates] = useState<
    Record<string, AssessmentState>
  >({});
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const summary = report?.summary ?? initialSummary;
  const items: readonly ReportItemSummary[] = report
    ? report.items.map((item) => ({
        criterion: item.criterion_id,
        id: item.report_item_id,
        observation: item.observation,
        rationale: item.rationale,
        state: item.assessment_state,
        uncertainty: item.uncertainty,
      }))
    : initialItems;

  async function loadReport() {
    if (!sessionId.trim()) return;
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const result = await api.getReport(sessionId.trim());
      if ("report_id" in result) {
        setReport(result);
        setProcessingMessage("");
        setStatus("Evidence 보고서를 불러왔습니다.");
      } else {
        setReport(null);
        setProcessingMessage(
          result.message ?? `보고서 처리 상태: ${result.status}`,
        );
      }
    } catch {
      setError("Evidence 보고서를 불러오지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function appendReview(item: ReportItemSummary) {
    if (!report) return;
    const reason = reviewReasons[item.id]?.trim() ?? "";
    if (!reason) {
      setError("사람 검토 이유를 입력해 주세요.");
      return;
    }
    setBusy(true);
    setStatus("");
    setError("");
    try {
      await api.createAssessmentReview(report.report_id, item.id, {
        assessment_state: reviewStates[item.id] ?? item.state,
        reason,
      });
      setStatus("사람 평가 검토가 원본과 분리되어 추가되었습니다.");
    } catch {
      setError("사람 평가 검토를 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="report-title">
      <h1 id="report-title">면접 Evidence 보고서</h1>
      <p>AI 원본은 변경되지 않습니다.</p>

      <label htmlFor="report-session-id">면접 세션 ID</label>
      <input
        id="report-session-id"
        value={sessionId}
        onChange={(event) => setSessionId(event.target.value)}
      />
      <button
        type="button"
        onClick={() => void loadReport()}
        disabled={busy || !sessionId.trim()}
      >
        {busy ? "보고서 확인 중" : "보고서 불러오기"}
      </button>

      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}
      {processingMessage && <p role="status">{processingMessage}</p>}
      <p>{summary}</p>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.criterion}</strong> {labels[item.state]}
            {item.observation && <p>{item.observation}</p>}
            {item.rationale && <p>근거: {item.rationale}</p>}
            {item.uncertainty && <p>불확실성: {item.uncertainty}</p>}
            {report && (
              <div>
                <label htmlFor={`review-state-${item.id}`}>
                  사람 검토 상태
                </label>
                <select
                  id={`review-state-${item.id}`}
                  value={reviewStates[item.id] ?? item.state}
                  onChange={(event) =>
                    setReviewStates((current) => ({
                      ...current,
                      [item.id]: event.target.value as AssessmentState,
                    }))
                  }
                >
                  {Object.entries(labels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <label htmlFor={`review-reason-${item.id}`}>
                  검토 이유 {item.criterion}
                </label>
                <textarea
                  id={`review-reason-${item.id}`}
                  value={reviewReasons[item.id] ?? ""}
                  onChange={(event) =>
                    setReviewReasons((current) => ({
                      ...current,
                      [item.id]: event.target.value,
                    }))
                  }
                />
                <button
                  type="button"
                  onClick={() => void appendReview(item)}
                  disabled={busy}
                >
                  사람 검토 추가
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
