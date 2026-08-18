import type {
  EquipmentCheck,
  InterviewResumeSnapshot,
  InterviewSessionView,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";
import { describe, expect, it, vi } from "vitest";

import { createInterviewApi, createProtocolMessage } from "../api";

describe("interview API", () => {
  it("records equipment, creates a session and retrieves recovery state", async () => {
    const equipment: EquipmentCheck = {
      camera: { status: "ready" },
      checked_at: "2026-08-18T00:00:00Z",
      equipment_check_id: "equipment-1",
      microphone: { status: "ready" },
      network: { status: "ready" },
      overall_status: "ready",
    };
    const session: InterviewSessionView = {
      interview_session_id: "0198b6c5-8800-7000-8000-000000000010",
      protocol_version: "1.0",
      session_sequence: 0,
      state: "preparing",
      websocket_path:
        "/v1/applicant/interview-sessions/0198b6c5-8800-7000-8000-000000000010/stream",
    };
    const snapshot: InterviewResumeSnapshot = {
      interview_session_id: session.interview_session_id,
      last_verified_recording_chunk_sequence: 2,
      server_sequence: 4,
      state: "paused",
    };
    const post = vi
      .fn()
      .mockResolvedValueOnce(equipment)
      .mockResolvedValueOnce(session);
    const get = vi.fn().mockResolvedValue(snapshot);
    const api = createInterviewApi({
      get,
      post,
    } as unknown as BrowserApiClient);

    await api.recordEquipmentCheck({
      camera: "ready",
      microphone: "ready",
      network: "ready",
    });
    await api.createSession("equipment-1", "strategy-1", false);
    await api.resumeSession(session.interview_session_id);

    expect(post).toHaveBeenNthCalledWith(
      1,
      "/applicant/equipment-checks",
      {
        camera: { status: "ready" },
        microphone: { status: "ready" },
        network: { status: "ready" },
      },
      { auth: "applicant" },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      "/applicant/interview-sessions",
      {
        acknowledged_partial_analysis: false,
        equipment_check_id: "equipment-1",
        strategy_id: "strategy-1",
      },
      { auth: "applicant" },
    );
    expect(get).toHaveBeenCalledWith(
      `/applicant/interview-sessions/${session.interview_session_id}/resume`,
      { auth: "applicant" },
    );
  });

  it("creates versioned websocket envelopes", () => {
    const message = createProtocolMessage(
      "0198b6c5-8800-7000-8000-000000000010",
      3,
      "question.repeat",
      { mode: "repeat_or_clarify", question_turn_id: "question-1" },
    );

    expect(message).toEqual(
      expect.objectContaining({
        message_type: "question.repeat",
        protocol_version: "1.0",
        sequence: 3,
        session_id: "0198b6c5-8800-7000-8000-000000000010",
      }),
    );
    expect(message.idempotency_key.length).toBeGreaterThanOrEqual(16);
  });
});
