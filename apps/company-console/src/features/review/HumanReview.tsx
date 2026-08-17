interface HumanReviewProps {
  readonly onDecision?: (
    decision: "advance" | "reject" | "hold" | "withdrawn",
  ) => void;
  readonly deletionStatus?: string;
}

export function HumanReview({
  onDecision,
  deletionStatus = "요청 없음",
}: HumanReviewProps) {
  return (
    <section aria-labelledby="human-review-title">
      <h2 id="human-review-title">사람 검토 기록</h2>
      <p>최종 결정은 회사 담당자만 기록할 수 있습니다.</p>
      <button type="button" onClick={() => onDecision?.("hold")}>
        보류 결정 기록
      </button>
      <button type="button" onClick={() => onDecision?.("advance")}>
        다음 단계 결정 기록
      </button>
      <p>삭제 상태: {deletionStatus}</p>
    </section>
  );
}
