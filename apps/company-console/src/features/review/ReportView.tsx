export interface ReportItemSummary {
  readonly id: string;
  readonly criterion: string;
  readonly state:
    | "confirmed"
    | "partially_confirmed"
    | "insufficient_evidence"
    | "needs_follow_up";
}

interface ReportViewProps {
  readonly summary: string;
  readonly items: readonly ReportItemSummary[];
}

const labels: Record<ReportItemSummary["state"], string> = {
  confirmed: "확인됨",
  partially_confirmed: "부분 확인",
  insufficient_evidence: "근거 부족",
  needs_follow_up: "추가 확인 필요",
};

export function ReportView({ summary, items }: ReportViewProps) {
  return (
    <section aria-labelledby="report-title">
      <h1 id="report-title">면접 Evidence 보고서</h1>
      <p>AI 원본은 변경되지 않습니다.</p>
      <p>{summary}</p>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.criterion}</strong> {labels[item.state]}
          </li>
        ))}
      </ul>
    </section>
  );
}
