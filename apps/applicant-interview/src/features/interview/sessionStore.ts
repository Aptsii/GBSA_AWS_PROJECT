import { createStore, StoreApi } from "zustand/vanilla";

export type InterviewSessionState =
  | "preparing"
  | "in_progress"
  | "awaiting_answer"
  | "preparing_question"
  | "paused"
  | "completed"
  | "report_generating"
  | "reviewable";

export interface ServerSessionEvent {
  readonly sequence: number;
  readonly state: InterviewSessionState;
  readonly lastFinalTurnId?: string;
  readonly pendingTurnId?: string;
  readonly degradedModes?: readonly string[];
  readonly lastVerifiedRecordingChunkSequence?: number;
}

export interface ResumeSnapshot {
  readonly serverSequence: number;
  readonly state: InterviewSessionState;
  readonly lastFinalTurnId?: string;
  readonly pendingTurnId?: string;
  readonly degradedModes?: readonly string[];
  readonly lastVerifiedRecordingChunkSequence?: number;
}

export interface InterviewSessionStore {
  readonly sequence: number;
  readonly state: InterviewSessionState;
  readonly connected: boolean;
  readonly lastFinalTurnId?: string;
  readonly pendingTurnId?: string;
  readonly degradedModes: readonly string[];
  readonly lastVerifiedRecordingChunkSequence: number;
  readonly applyServerEvent: (event: ServerSessionEvent) => void;
  readonly resume: (snapshot: ResumeSnapshot) => void;
  readonly markDisconnected: () => void;
}

export function createSessionStore(): StoreApi<InterviewSessionStore> {
  return createStore<InterviewSessionStore>((set, get) => ({
    sequence: 0,
    state: "preparing",
    connected: false,
    degradedModes: [],
    lastVerifiedRecordingChunkSequence: 0,
    applyServerEvent: (event) => {
      if (event.sequence <= get().sequence) return;
      set({
        sequence: event.sequence,
        state: event.state,
        connected: true,
        lastFinalTurnId: event.lastFinalTurnId ?? get().lastFinalTurnId,
        pendingTurnId: event.pendingTurnId ?? get().pendingTurnId,
        degradedModes: event.degradedModes ?? get().degradedModes,
        lastVerifiedRecordingChunkSequence:
          event.lastVerifiedRecordingChunkSequence ??
          get().lastVerifiedRecordingChunkSequence,
      });
    },
    resume: (snapshot) => {
      if (snapshot.serverSequence < get().sequence) return;
      set({
        sequence: snapshot.serverSequence,
        state: snapshot.state,
        connected: true,
        lastFinalTurnId: snapshot.lastFinalTurnId,
        pendingTurnId: snapshot.pendingTurnId,
        degradedModes: snapshot.degradedModes ?? [],
        lastVerifiedRecordingChunkSequence:
          snapshot.lastVerifiedRecordingChunkSequence ?? 0,
      });
    },
    markDisconnected: () => set({ connected: false }),
  }));
}
