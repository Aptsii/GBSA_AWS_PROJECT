import type {
  AnalysisReadiness,
  SubmissionView,
} from "@interview-evidence/contracts";
import { ApiProblem } from "@interview-evidence/web-client";
import {
  ChangeEvent,
  FormEvent,
  useCallback,
  useEffect,
  useState,
} from "react";

import { updateApplicantProgress } from "../../app/progress";
import { submissionApi, type SubmissionApi } from "./api";

interface SubmissionJourneyProps {
  readonly api?: SubmissionApi;
  readonly pollIntervalMs?: number;
}

const statusLabels: Record<SubmissionView["status"], string> = {
  analyzing: "분석 중",
  deleted: "삭제됨",
  failed: "분석 실패",
  partial: "부분 완료",
  ready: "준비 완료",
  received: "접수됨",
  validating: "검증 중",
};

export function SubmissionJourney({
  api = submissionApi,
  pollIntervalMs = 2_000,
}: SubmissionJourneyProps) {
  const [file, setFile] = useState<File>();
  const [publicUrl, setPublicUrl] = useState("");
  const [readiness, setReadiness] = useState<AnalysisReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getReadiness();
      setReadiness(next);
      if (next.strategy_id) {
        updateApplicantProgress({
          acknowledgedPartialAnalysis: next.overall_status === "partial",
          strategyId: next.strategy_id,
        });
      }
      setError(null);
    } catch (caught) {
      setError(problemMessage(caught));
    }
  }, [api]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (pollIntervalMs <= 0 || !readiness) return;
    if (!new Set(["waiting", "analyzing"]).has(readiness.overall_status))
      return;
    const timer = window.setInterval(() => void refresh(), pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [pollIntervalMs, readiness, refresh]);

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0]);
  }

  async function submit(
    event: FormEvent<HTMLFormElement>,
    operation: () => Promise<void>,
  ) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await operation();
      await refresh();
    } catch (caught) {
      setError(problemMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="submission-title">
      <p>면접 준비 자료</p>
      <h1 id="submission-title">지원 자료 제출</h1>
      <p>
        제출 자료는 질문 준비에만 사용되며 그 자체가 평가 근거가 되지 않습니다.
      </p>
      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}

      <form
        onSubmit={(event) =>
          void submit(event, async () => {
            if (!file) return;
            await api.submitFile(file);
            setStatus("문서가 API에 접수되었습니다.");
            setFile(undefined);
          })
        }
      >
        <label htmlFor="submission-file">문서 파일</label>
        <input
          id="submission-file"
          type="file"
          accept="application/pdf,text/plain,text/markdown"
          onChange={selectFile}
        />
        <button type="submit" disabled={!file || busy}>
          {busy ? "제출 중" : "문서 제출"}
        </button>
      </form>

      <form
        onSubmit={(event) =>
          void submit(event, async () => {
            const normalized = publicUrl.trim();
            if (!normalized) return;
            await api.submitRepository(normalized);
            setStatus("저장소가 API에 접수되었습니다.");
            setPublicUrl("");
          })
        }
      >
        <label htmlFor="public-repository">공개 저장소 주소</label>
        <input
          id="public-repository"
          type="url"
          value={publicUrl}
          onChange={(event) => setPublicUrl(event.target.value)}
          placeholder="https://github.com/owner/repository"
        />
        <button type="submit" disabled={!publicUrl.trim() || busy}>
          {busy ? "제출 중" : "저장소 제출"}
        </button>
      </form>

      <button type="button" onClick={() => void refresh()} disabled={busy}>
        분석 상태 새로고침
      </button>
      {readiness && (
        <div>
          <p>전체 상태: {overallStatusLabel(readiness.overall_status)}</p>
          <p>면접 진행 가능: {readiness.interview_ready ? "예" : "아니요"}</p>
          {readiness.impact_summary && <p>{readiness.impact_summary}</p>}
          {readiness.strategy_id && <p>전략 ID: {readiness.strategy_id}</p>}
        </div>
      )}

      <ul aria-label="제출 자료 상태">
        {(readiness?.submissions ?? []).map((submission) => (
          <li key={submission.submission_id}>
            <strong>{submission.source_type}</strong>
            <span>{statusLabels[submission.status]}</span>
            {submission.impact_summary && <p>{submission.impact_summary}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default SubmissionJourney;

function overallStatusLabel(
  status: AnalysisReadiness["overall_status"],
): string {
  return {
    analyzing: "분석 중",
    failed: "실패",
    partial: "부분 완료",
    ready: "준비 완료",
    waiting: "대기 중",
  }[status];
}

function problemMessage(caught: unknown): string {
  if (caught instanceof ApiProblem) {
    return caught.detail
      ? `${caught.message}: ${caught.detail}`
      : caught.message;
  }
  return "지원 자료 API 요청 중 오류가 발생했습니다.";
}
