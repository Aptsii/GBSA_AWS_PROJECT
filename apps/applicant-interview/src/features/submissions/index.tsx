import { ChangeEvent, FormEvent, useState } from "react";

export interface SubmissionStatusItem {
  readonly id: string;
  readonly label: string;
  readonly status: "received" | "analyzing" | "ready" | "partial" | "failed";
  readonly impactSummary?: string;
}

interface SubmissionJourneyProps {
  readonly initialSubmissions?: readonly SubmissionStatusItem[];
  readonly onSubmit?: (submission: {
    sourceType: "pdf" | "public_git";
    file?: File;
    publicUrl?: string;
  }) => void;
}

const statusLabels: Record<SubmissionStatusItem["status"], string> = {
  received: "접수됨",
  analyzing: "분석 중",
  ready: "준비 완료",
  partial: "부분 완료",
  failed: "분석 실패",
};

export function SubmissionJourney({
  initialSubmissions = [],
  onSubmit,
}: SubmissionJourneyProps) {
  const [file, setFile] = useState<File>();
  const [publicUrl, setPublicUrl] = useState("");

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0]);
  }

  function submitFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (file) onSubmit?.({ sourceType: "pdf", file });
  }

  function submitRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (publicUrl.trim()) {
      onSubmit?.({ sourceType: "public_git", publicUrl: publicUrl.trim() });
    }
  }

  return (
    <section aria-labelledby="submission-title">
      <p>면접 준비 자료</p>
      <h1 id="submission-title">지원 자료 제출</h1>
      <p>제출 자료는 질문 준비에만 사용되며 그 자체가 평가 근거가 되지 않습니다.</p>

      <form onSubmit={submitFile}>
        <label htmlFor="submission-file">문서 파일</label>
        <input
          id="submission-file"
          type="file"
          accept="application/pdf,text/plain,text/markdown"
          onChange={selectFile}
        />
        <button type="submit" disabled={!file}>
          문서 제출
        </button>
      </form>

      <form onSubmit={submitRepository}>
        <label htmlFor="public-repository">공개 저장소 주소</label>
        <input
          id="public-repository"
          type="url"
          value={publicUrl}
          onChange={(event) => setPublicUrl(event.target.value)}
          placeholder="https://github.com/owner/repository"
        />
        <button type="submit" disabled={!publicUrl.trim()}>
          저장소 제출
        </button>
      </form>

      <ul aria-label="제출 자료 상태">
        {initialSubmissions.map((submission) => (
          <li key={submission.id}>
            <strong>{submission.label}</strong>
            <span>{statusLabels[submission.status]}</span>
            {submission.impactSummary && <p>{submission.impactSummary}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default SubmissionJourney;
