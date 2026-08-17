import { useState } from "react";

export type InterviewRoomPhase =
  "question" | "answering" | "processing" | "paused" | "completed";

interface InterviewRoomProps {
  readonly question: string;
  readonly textOnly?: boolean;
  readonly phase?: InterviewRoomPhase;
  readonly onCompleteAnswer?: () => void;
  readonly onRepeatQuestion?: () => void;
}

const phaseMessages: Record<InterviewRoomPhase, string> = {
  question: "질문을 확인해 주세요.",
  answering: "답변을 마치면 답변 완료를 눌러 주세요.",
  processing: "답변을 안전하게 처리하고 다음 질문을 준비하고 있습니다.",
  paused: "연결 상태를 확인하고 있습니다. 평가에는 영향을 주지 않습니다.",
  completed: "면접이 완료되었습니다. 제출 상태를 확인해 주세요.",
};

export function InterviewRoom({
  question,
  textOnly = false,
  phase = "answering",
  onCompleteAnswer,
  onRepeatQuestion,
}: InterviewRoomProps) {
  const [answerDraft, setAnswerDraft] = useState("");
  const canAnswer = phase === "question" || phase === "answering";

  return (
    <main aria-labelledby="interview-room-title">
      <header>
        <p>AI 진행 면접</p>
        <h1 id="interview-room-title">구조화 면접실</h1>
        <p>
          AI가 정해진 평가 기준에 따라 질문을 진행합니다. 최종 채용 결정은
          담당자가 직접 내립니다.
        </p>
      </header>

      {textOnly && <p role="status">음성 없이 텍스트로 진행합니다.</p>}
      <p role="status">{phaseMessages[phase]}</p>

      <section aria-labelledby="current-question-title">
        <h2 id="current-question-title">현재 질문</h2>
        <p>{question}</p>
        <button type="button" onClick={onRepeatQuestion} disabled={!canAnswer}>
          질문 다시 듣기
        </button>
      </section>

      <section aria-labelledby="answer-title">
        <h2 id="answer-title">내 답변</h2>
        {textOnly && (
          <textarea
            aria-label="답변 내용"
            value={answerDraft}
            onChange={(event) => setAnswerDraft(event.target.value)}
            disabled={!canAnswer}
          />
        )}
        <button type="button" onClick={onCompleteAnswer} disabled={!canAnswer}>
          답변 완료
        </button>
      </section>
    </main>
  );
}
