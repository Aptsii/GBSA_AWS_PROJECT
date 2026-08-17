import { describe, expect, it } from "vitest";

import { createSessionStore } from "../sessionStore";

describe("면접 세션 복구 store", () => {
  it("서버 sequence가 더 최신이면 resume snapshot으로 교체한다", () => {
    const store = createSessionStore();
    store.getState().applyServerEvent({
      sequence: 2,
      state: "awaiting_answer",
      lastFinalTurnId: "t1",
    });
    store.getState().resume({
      serverSequence: 5,
      state: "paused",
      lastFinalTurnId: "t2",
      degradedModes: ["search_fallback"],
    });
    expect(store.getState().sequence).toBe(5);
    expect(store.getState().lastFinalTurnId).toBe("t2");
    expect(store.getState().degradedModes).toEqual(["search_fallback"]);
  });
});
