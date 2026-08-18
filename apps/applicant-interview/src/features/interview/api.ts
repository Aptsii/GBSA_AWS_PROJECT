import type {
  EquipmentCheck,
  EquipmentCheckCreate,
  InterviewResumeSnapshot,
  InterviewSessionCreate,
  InterviewSessionView,
  RecordingUploadIntentCreate,
} from "@interview-evidence/contracts";
import {
  createIdempotencyKey,
  createUuid7,
  createWebSocketUrl,
  type BrowserApiClient,
} from "@interview-evidence/web-client";

import { apiBaseUrl, apiClient } from "../../app/api";
import type { RecordingChunkPayload } from "./media";

export type EquipmentStatus = "ready" | "warning" | "failed";

export interface EquipmentStatusInput {
  readonly camera: EquipmentStatus;
  readonly microphone: EquipmentStatus;
  readonly network: EquipmentStatus;
}

interface RecordingUploadIntent {
  readonly recording_chunk_id: string;
  readonly upload_id: string;
  readonly method: "PUT";
  readonly url: string;
  readonly required_headers: Record<string, unknown>;
  readonly expires_at: string;
}

export interface InterviewApi {
  recordEquipmentCheck(
    readiness: EquipmentStatusInput,
  ): Promise<EquipmentCheck>;
  createSession(
    equipmentCheckId: string,
    strategyId: string,
    acknowledgedPartialAnalysis: boolean,
  ): Promise<InterviewSessionView>;
  resumeSession(sessionId: string): Promise<InterviewResumeSnapshot>;
  uploadRecordingChunk(
    sessionId: string,
    chunk: RecordingChunkPayload,
  ): Promise<void>;
}

export interface ProtocolMessage {
  readonly protocol_version: "1.0";
  readonly message_type: string;
  readonly session_id: string;
  readonly sequence: number;
  readonly idempotency_key: string;
  readonly correlation_id: string;
  readonly sent_at: string;
  readonly payload: Record<string, unknown>;
}

export interface InterviewSocket {
  start(equipmentCheckId: string): void;
  repeatQuestion(questionTurnId: string): void;
  completeAnswer(
    answerTurnId: string,
    progress: {
      readonly lastAudioChunkSequence: number;
      readonly lastRecordingChunkSequence: number;
    },
  ): void;
  resume(snapshot: InterviewResumeSnapshot): void;
  close(): void;
}

export interface InterviewSocketOptions {
  readonly sessionId: string;
  readonly websocketPath: string;
  readonly onMessage: (message: ProtocolMessage) => void;
  readonly onOpen?: () => void;
  readonly onClose?: () => void;
  readonly WebSocketImplementation?: typeof WebSocket;
}

export type InterviewSocketFactory = (
  options: InterviewSocketOptions,
) => InterviewSocket;

export function createInterviewApi(client: BrowserApiClient): InterviewApi {
  return {
    recordEquipmentCheck(readiness) {
      const payload: EquipmentCheckCreate = {
        camera: { status: readiness.camera },
        microphone: { status: readiness.microphone },
        network: { status: readiness.network },
      };
      return client.post<EquipmentCheck, EquipmentCheckCreate>(
        "/applicant/equipment-checks",
        payload,
        { auth: "applicant" },
      );
    },
    createSession(equipmentCheckId, strategyId, acknowledgedPartialAnalysis) {
      const payload: InterviewSessionCreate = {
        acknowledged_partial_analysis: acknowledgedPartialAnalysis,
        equipment_check_id: equipmentCheckId,
        strategy_id: strategyId,
      };
      return client.post<InterviewSessionView, InterviewSessionCreate>(
        "/applicant/interview-sessions",
        payload,
        { auth: "applicant" },
      );
    },
    resumeSession(sessionId) {
      return client.get<InterviewResumeSnapshot>(
        `/applicant/interview-sessions/${sessionId}/resume`,
        { auth: "applicant" },
      );
    },
    async uploadRecordingChunk(sessionId, chunk) {
      const payload: RecordingUploadIntentCreate = {
        byte_size: chunk.byteSize,
        chunk_sequence: chunk.sequence,
        session_end_ms: chunk.endMs,
        session_start_ms: chunk.startMs,
        sha256: chunk.sha256,
      };
      const intent = await client.post<
        RecordingUploadIntent,
        RecordingUploadIntentCreate
      >(
        `/applicant/interview-sessions/${sessionId}/media-upload-intents`,
        payload,
        { auth: "applicant" },
      );
      const requiredHeaders = stringHeaders(intent.required_headers);
      await client.upload(intent.url, chunk.blob, {
        contentType:
          requiredHeaders["content-type"] ??
          (chunk.blob.type || "application/octet-stream"),
        headers: requiredHeaders,
      });
    },
  };
}

export function createProtocolMessage(
  sessionId: string,
  sequence: number,
  messageType: string,
  payload: Record<string, unknown>,
): ProtocolMessage {
  return {
    correlation_id: createUuid7(),
    idempotency_key: createIdempotencyKey(messageType),
    message_type: messageType,
    payload,
    protocol_version: "1.0",
    sent_at: new Date().toISOString(),
    sequence,
    session_id: sessionId,
  };
}

export function createInterviewSocket(
  options: InterviewSocketOptions,
): InterviewSocket {
  const Socket = options.WebSocketImplementation ?? WebSocket;
  const url = options.websocketPath.startsWith("/v1/")
    ? createWebSocketUrl(globalThis.location.origin, options.websocketPath)
    : createWebSocketUrl(apiBaseUrl, options.websocketPath);
  const socket = new Socket(url);
  let serverSequence = 0;

  socket.addEventListener("open", () => options.onOpen?.());
  socket.addEventListener("close", () => options.onClose?.());
  socket.addEventListener("message", (event) => {
    if (typeof event.data !== "string") return;
    try {
      const message = JSON.parse(event.data) as ProtocolMessage;
      if (
        message.protocol_version !== "1.0" ||
        message.session_id !== options.sessionId ||
        message.sequence < serverSequence
      ) {
        return;
      }
      serverSequence = message.sequence;
      options.onMessage(message);
    } catch {
      // Invalid server frames are ignored and never reflected into applicant content.
    }
  });

  function send(messageType: string, payload: Record<string, unknown>): void {
    const message = createProtocolMessage(
      options.sessionId,
      serverSequence,
      messageType,
      payload,
    );
    const write = () => socket.send(JSON.stringify(message));
    if (socket.readyState === Socket.OPEN) write();
    else socket.addEventListener("open", write, { once: true });
  }

  return {
    start(equipmentCheckId) {
      send("session.start", {
        equipment_check_id: equipmentCheckId,
        expected_state: "preparing",
      });
    },
    repeatQuestion(questionTurnId) {
      send("question.repeat", {
        mode: "repeat_or_clarify",
        question_turn_id: questionTurnId,
      });
    },
    completeAnswer(answerTurnId, progress) {
      send("answer.complete", {
        answer_turn_id: answerTurnId,
        expected_state: "awaiting_answer",
        last_audio_chunk_sequence: progress.lastAudioChunkSequence,
        last_recording_chunk_sequence: progress.lastRecordingChunkSequence,
      });
    },
    resume(snapshot) {
      send("session.resume", {
        last_applied_server_sequence: snapshot.server_sequence,
        last_final_turn_id: snapshot.last_final_turn_id ?? null,
        last_uploaded_recording_chunk_sequence:
          snapshot.last_verified_recording_chunk_sequence,
      });
    },
    close() {
      socket.close(1000, "applicant_navigation");
    },
  };
}

export const interviewApi = createInterviewApi(apiClient);

function stringHeaders(
  values: Record<string, unknown>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}
