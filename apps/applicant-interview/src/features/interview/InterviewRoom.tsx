import { useEffect, useRef, useState } from "react";

import { createUuid7 } from "@interview-evidence/web-client";

import {
  getApplicantProgress,
  updateApplicantProgress,
  type ApplicantProgress,
} from "../../app/progress";
import { Avatar, type AvatarSpeechMark } from "./Avatar";
import {
  createInterviewSocket,
  interviewApi,
  type InterviewApi,
  type InterviewSocket,
  type InterviewSocketFactory,
  type ProtocolMessage,
} from "./api";
import { ChunkedRecorder } from "./media";

export type InterviewRoomPhase =
  "question" | "answering" | "processing" | "paused" | "completed";

interface InterviewRoomProps {
  readonly api?: InterviewApi;
  readonly initialProgress?: ApplicantProgress;
  readonly mediaStreamFactory?: () => Promise<MediaStream>;
  readonly question?: string;
  readonly textOnly?: boolean;
  readonly phase?: InterviewRoomPhase;
  readonly speechMarks?: readonly AvatarSpeechMark[];
  readonly socketFactory?: InterviewSocketFactory;
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
  api = interviewApi,
  initialProgress,
  mediaStreamFactory = defaultMediaStreamFactory,
  question: initialQuestion = "면접 세션을 시작하면 질문이 표시됩니다.",
  textOnly: initialTextOnly = false,
  phase: initialPhase = "paused",
  speechMarks = [],
  socketFactory = createInterviewSocket,
  onCompleteAnswer,
  onRepeatQuestion,
}: InterviewRoomProps) {
  const [startingProgress] = useState<ApplicantProgress>(
    () => initialProgress ?? getApplicantProgress(),
  );
  const progressRef = useRef<ApplicantProgress>(startingProgress);
  const socketRef = useRef<InterviewSocket | undefined>(undefined);
  const recorderRef = useRef<ChunkedRecorder | undefined>(undefined);
  const mediaStreamRef = useRef<MediaStream | undefined>(undefined);
  const lastServerSequenceRef = useRef(0);
  const lastRecordingChunkSequenceRef = useRef(0);
  const [question, setQuestion] = useState(initialQuestion);
  const [textOnly, setTextOnly] = useState(initialTextOnly);
  const [phase, setPhase] = useState<InterviewRoomPhase>(initialPhase);
  const [answerDraft, setAnswerDraft] = useState("");
  const [transcript, setTranscript] = useState("");
  const [questionTurnId, setQuestionTurnId] = useState<string>();
  const [answerTurnId, setAnswerTurnId] = useState<string>();
  const [connectionMessage, setConnectionMessage] = useState("연결 대기 중");
  const [degradedModes, setDegradedModes] = useState<readonly string[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [starting, setStarting] = useState(false);
  const [started, setStarted] = useState(
    Boolean(startingProgress.interviewSessionId),
  );

  useEffect(
    () => () => {
      socketRef.current?.close();
      void recorderRef.current?.stop();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  const canAnswer =
    Boolean(answerTurnId) && (phase === "question" || phase === "answering");

  async function startSession() {
    const progress = progressRef.current;
    if (!progress.equipmentCheckId || !progress.strategyId) {
      setErrorMessage(
        "장비 점검과 지원 자료 분석을 완료한 뒤 면접을 시작해 주세요.",
      );
      return;
    }

    setStarting(true);
    setErrorMessage("");
    setConnectionMessage("세션 연결 중");
    try {
      if (progress.interviewSessionId && progress.websocketPath) {
        const snapshot = await api.resumeSession(progress.interviewSessionId);
        applyResumeSnapshot(snapshot);
        connectSocket(
          progress.interviewSessionId,
          progress.websocketPath,
          (socket) => socket.resume(snapshot),
        );
        await startRecorder(progress.interviewSessionId);
      } else {
        const session = await api.createSession(
          progress.equipmentCheckId,
          progress.strategyId,
          progress.acknowledgedPartialAnalysis ?? false,
        );
        progressRef.current = updateApplicantProgress({
          interviewSessionId: session.interview_session_id,
          websocketPath: session.websocket_path,
        });
        connectSocket(
          session.interview_session_id,
          session.websocket_path,
          (socket) => socket.start(progress.equipmentCheckId!),
        );
        await startRecorder(session.interview_session_id);
      }
      setStarted(true);
      setConnectionMessage("실시간 연결됨");
    } catch {
      setPhase("paused");
      setConnectionMessage("연결 실패");
      setErrorMessage(
        "면접 세션을 연결하지 못했습니다. 저장된 진행 상태로 다시 시도할 수 있습니다.",
      );
    } finally {
      setStarting(false);
    }
  }

  function connectSocket(
    sessionId: string,
    websocketPath: string,
    afterConnect: (socket: InterviewSocket) => void,
  ) {
    socketRef.current?.close();
    const socket = socketFactory({
      sessionId,
      websocketPath,
      onMessage: handleServerMessage,
      onOpen: () => {
        setConnectionMessage("실시간 연결됨");
        void recorderRef.current?.retryPending();
      },
      onClose: () => {
        setConnectionMessage("연결 끊김 · 복구 가능");
        setPhase((current) => (current === "completed" ? current : "paused"));
      },
    });
    socketRef.current = socket;
    afterConnect(socket);
  }

  async function startRecorder(sessionId: string) {
    if (typeof MediaRecorder === "undefined") return;
    try {
      const stream = await mediaStreamFactory();
      mediaStreamRef.current = stream;
      const recorder = new ChunkedRecorder(stream, sessionId, async (chunk) => {
        await api.uploadRecordingChunk(sessionId, chunk);
        lastRecordingChunkSequenceRef.current = Math.max(
          lastRecordingChunkSequenceRef.current,
          chunk.sequence,
        );
      });
      recorderRef.current = recorder;
      await recorder.retryPending();
      recorder.start();
    } catch {
      setDegradedModes((current) =>
        unique([...current, "recording_unavailable"]),
      );
    }
  }

  function handleServerMessage(message: ProtocolMessage) {
    if (message.sequence < lastServerSequenceRef.current) return;
    lastServerSequenceRef.current = message.sequence;

    switch (message.message_type) {
      case "question.preparing": {
        setPhase("processing");
        const degradedMode = readString(message.payload, "degraded_mode");
        if (degradedMode && degradedMode !== "none") {
          setDegradedModes((current) => unique([...current, degradedMode]));
          if (degradedMode === "text_only") setTextOnly(true);
        }
        break;
      }
      case "question.ready": {
        const nextQuestion = readString(message.payload, "text");
        const nextQuestionTurnId = readString(
          message.payload,
          "question_turn_id",
        );
        const nextAnswerTurnId =
          readString(message.payload, "answer_turn_id") ?? createUuid7();
        if (nextQuestion) setQuestion(nextQuestion);
        setQuestionTurnId(nextQuestionTurnId);
        setAnswerTurnId(nextAnswerTurnId);
        setTextOnly(readBoolean(message.payload, "text_only") ?? false);
        setAnswerDraft("");
        setTranscript("");
        setPhase("answering");
        break;
      }
      case "transcript.partial":
      case "transcript.final": {
        setTranscript(readString(message.payload, "text") ?? "");
        break;
      }
      case "session.state_changed": {
        setPhase(phaseFromServerState(readString(message.payload, "state")));
        break;
      }
      case "resume.snapshot": {
        applyResumePayload(message.payload);
        break;
      }
      case "session.paused": {
        setPhase("paused");
        break;
      }
      case "session.completed": {
        setPhase("completed");
        void recorderRef.current?.stop();
        break;
      }
      case "error": {
        setErrorMessage(
          readString(message.payload, "safe_message") ??
            "면접 처리 중 오류가 발생했습니다. 진행 상태는 보존됩니다.",
        );
        break;
      }
    }
  }

  function applyResumeSnapshot(snapshot: {
    readonly server_sequence: number;
    readonly state: string;
    readonly last_verified_recording_chunk_sequence: number;
    readonly degraded_modes?: readonly string[];
    readonly pending_turn?: Record<string, unknown> | null;
  }) {
    lastServerSequenceRef.current = snapshot.server_sequence;
    lastRecordingChunkSequenceRef.current =
      snapshot.last_verified_recording_chunk_sequence;
    setPhase(phaseFromServerState(snapshot.state));
    setDegradedModes(snapshot.degraded_modes ?? []);
    const pendingTurnId = snapshot.pending_turn
      ? readString(snapshot.pending_turn, "turn_id")
      : undefined;
    if (pendingTurnId) setQuestionTurnId(pendingTurnId);
  }

  function applyResumePayload(payload: Record<string, unknown>) {
    const serverSequence = readNumber(payload, "server_sequence") ?? 0;
    lastServerSequenceRef.current = Math.max(
      lastServerSequenceRef.current,
      serverSequence,
    );
    lastRecordingChunkSequenceRef.current = Math.max(
      lastRecordingChunkSequenceRef.current,
      readNumber(payload, "last_verified_recording_chunk_sequence") ?? 0,
    );
    setPhase(phaseFromServerState(readString(payload, "state")));
    const modes = payload.degraded_modes;
    if (Array.isArray(modes)) {
      setDegradedModes(
        modes.filter((mode): mode is string => typeof mode === "string"),
      );
    }
  }

  function repeatQuestion() {
    if (!questionTurnId) return;
    socketRef.current?.repeatQuestion(questionTurnId);
    onRepeatQuestion?.();
  }

  function completeAnswer() {
    if (!answerTurnId) return;
    socketRef.current?.completeAnswer(answerTurnId, {
      lastAudioChunkSequence: 0,
      lastRecordingChunkSequence: lastRecordingChunkSequenceRef.current,
    });
    setPhase("processing");
    onCompleteAnswer?.();
  }

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

      <p role="status">{connectionMessage}</p>
      {!started && (
        <button
          type="button"
          onClick={() => void startSession()}
          disabled={starting}
        >
          {starting ? "면접 세션 연결 중" : "면접 세션 시작"}
        </button>
      )}
      {started && phase === "paused" && (
        <button
          type="button"
          onClick={() => void startSession()}
          disabled={starting}
        >
          {starting ? "면접 세션 복구 중" : "면접 세션 재개"}
        </button>
      )}

      {textOnly && <p role="status">음성 없이 텍스트로 진행합니다.</p>}
      <p role="status">{phaseMessages[phase]}</p>
      {degradedModes.length > 0 && (
        <p role="status">제한 모드: {degradedModes.join(", ")}</p>
      )}
      {errorMessage && <p role="alert">{errorMessage}</p>}

      <Avatar
        speaking={phase === "question"}
        textOnly={textOnly}
        speechMarks={speechMarks}
      />

      <section aria-labelledby="current-question-title">
        <h2 id="current-question-title">현재 질문</h2>
        <p>{question}</p>
        <button
          type="button"
          onClick={repeatQuestion}
          disabled={!questionTurnId}
        >
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
        {transcript && <p aria-label="실시간 자막">{transcript}</p>}
        <button type="button" onClick={completeAnswer} disabled={!canAnswer}>
          답변 완료
        </button>
      </section>
    </main>
  );
}

async function defaultMediaStreamFactory(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("media_devices_unavailable");
  }
  return navigator.mediaDevices.getUserMedia({ audio: true, video: true });
}

function phaseFromServerState(state?: string): InterviewRoomPhase {
  switch (state) {
    case "in_progress":
      return "question";
    case "awaiting_answer":
      return "answering";
    case "preparing":
    case "preparing_question":
    case "report_generating":
      return "processing";
    case "completed":
    case "reviewable":
      return "completed";
    default:
      return "paused";
  }
}

function readString(
  payload: Record<string, unknown>,
  key: string,
): string | undefined {
  const value = payload[key];
  return typeof value === "string" ? value : undefined;
}

function readBoolean(
  payload: Record<string, unknown>,
  key: string,
): boolean | undefined {
  const value = payload[key];
  return typeof value === "boolean" ? value : undefined;
}

function readNumber(
  payload: Record<string, unknown>,
  key: string,
): number | undefined {
  const value = payload[key];
  return typeof value === "number" ? value : undefined;
}

function unique(values: readonly string[]): readonly string[] {
  return [...new Set(values)];
}
