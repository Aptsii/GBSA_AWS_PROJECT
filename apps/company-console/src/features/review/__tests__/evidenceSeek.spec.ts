import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TimelineView } from "../TimelineView";

describe("Evidence 영상 탐색", () => {
  it("서명 재생 URL을 조회하고 실제 재생 시작을 2초 안에 측정한다", async () => {
    const onSeek = vi.fn();
    const onPlaybackStart = vi.fn();
    const requestPlayback = vi.fn().mockResolvedValue({
      url: "https://media.example.invalid/signed/evidence.webm",
      expiresAt: "2099-08-17T13:05:00Z",
    });
    const now = vi.fn().mockReturnValueOnce(100).mockReturnValueOnce(450);
    render(
      React.createElement(TimelineView, {
        entries: [
          { id: "e1", text: "복구 답변", startMs: 4200, evidence: true },
        ],
        onSeek,
        onPlaybackStart,
        requestPlayback,
        now,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "복구 답변" }));

    await waitFor(() => expect(requestPlayback).toHaveBeenCalledTimes(1));
    const video = (await screen.findByLabelText(
      "Evidence 영상",
    )) as HTMLVideoElement;
    const play = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(video, "play", { configurable: true, value: play });
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(4.2);
    fireEvent.seeked(video);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    fireEvent.playing(video);

    expect(onSeek).toHaveBeenCalledWith(4200);
    expect(onPlaybackStart).toHaveBeenCalledWith({
      elapsedMs: 350,
      entryId: "e1",
      seekOffsetMs: 0,
      withinThreshold: true,
    });
    expect(screen.getByText("재생 시작: 350ms")).toBeInTheDocument();
  });
});
