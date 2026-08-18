import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { InterviewApi, InterviewSocket, ProtocolMessage } from "../api";
import { EquipmentCheck } from "../EquipmentCheck";
import { InterviewRoom } from "../InterviewRoom";

describe("복구 가능한 면접 여정", () => {
  it("장비 점검 결과를 API에 기록한다", async () => {
    const onReady = vi.fn();
    const api: InterviewApi = {
      createSession: vi.fn(),
      recordEquipmentCheck: vi.fn().mockResolvedValue({
        camera: { status: "warning" },
        checked_at: "2026-08-18T00:00:00Z",
        equipment_check_id: "equipment-1",
        microphone: { status: "warning" },
        network: { status: "ready" },
        overall_status: "warning",
      }),
      resumeSession: vi.fn(),
      uploadRecordingChunk: vi.fn(),
    };
    render(<EquipmentCheck api={api} onReady={onReady} />);

    fireEvent.click(screen.getByRole("button", { name: "장비 점검 완료" }));

    expect(
      await screen.findByText("장비 점검 결과가 API에 저장되었습니다."),
    ).toBeDefined();
    expect(onReady).toHaveBeenCalledWith(
      expect.objectContaining({ equipment_check_id: "equipment-1" }),
    );
  });

  it("세션과 WebSocket을 시작하고 서버 질문에 답변 완료를 전송한다", async () => {
    let onMessage: ((message: ProtocolMessage) => void) | undefined;
    const socket: InterviewSocket = {
      close: vi.fn(),
      completeAnswer: vi.fn(),
      repeatQuestion: vi.fn(),
      resume: vi.fn(),
      start: vi.fn(),
      submitTextAnswer: vi.fn(),
    };
    const socketFactory = vi.fn(
      (options: { onMessage: (message: ProtocolMessage) => void }) => {
        onMessage = options.onMessage;
        return socket;
      },
    );
    const api: InterviewApi = {
      createSession: vi.fn().mockResolvedValue({
        interview_session_id: "0198b6c5-8800-7000-8000-000000000010",
        protocol_version: "1.0",
        session_sequence: 0,
        state: "preparing",
        websocket_path:
          "/v1/applicant/interview-sessions/0198b6c5-8800-7000-8000-000000000010/stream",
      }),
      recordEquipmentCheck: vi.fn(),
      resumeSession: vi.fn(),
      uploadRecordingChunk: vi.fn(),
    };
    render(
      <InterviewRoom
        api={api}
        initialProgress={{
          equipmentCheckId: "equipment-1",
          strategyId: "strategy-1",
        }}
        socketFactory={socketFactory}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "면접 세션 시작" }));
    expect(await screen.findByText("실시간 연결됨")).toBeDefined();
    expect(socket.start).toHaveBeenCalledWith("equipment-1");

    onMessage?.({
      correlation_id: "0198b6c5-8800-7000-8000-000000000012",
      idempotency_key: "server-question-1",
      message_type: "question.ready",
      protocol_version: "1.0",
      sequence: 1,
      sent_at: "2026-08-18T00:00:00Z",
      session_id: "0198b6c5-8800-7000-8000-000000000010",
      payload: {
        question_turn_id: "question-1",
        text: "설계 이유를 설명해 주세요.",
        text_only: true,
      },
    });
    expect(await screen.findByText("설계 이유를 설명해 주세요.")).toBeDefined();
    fireEvent.change(screen.getByLabelText("답변 내용"), {
      target: { value: "장애 격리를 위해 비동기 경계를 선택했습니다." },
    });
    fireEvent.click(screen.getByRole("button", { name: "답변 완료" }));

    expect(socket.submitTextAnswer).toHaveBeenCalledWith(
      expect.any(String),
      "장애 격리를 위해 비동기 경계를 선택했습니다.",
    );
    expect(socket.completeAnswer).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ lastRecordingChunkSequence: 0 }),
    );
  });
});
