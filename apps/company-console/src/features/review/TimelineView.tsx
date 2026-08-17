import { useRef, useState } from "react";

export const MAXIMUM_PLAYBACK_START_MS = 2000;

export interface TimelineEntryView {
  readonly id: string;
  readonly text: string;
  readonly startMs: number;
  readonly evidence?: boolean;
}

export interface PlaybackReferenceView {
  readonly url: string;
  readonly expiresAt: string;
}

export interface PlaybackStartMeasurement {
  readonly elapsedMs: number;
  readonly entryId: string;
  readonly seekOffsetMs: number;
  readonly withinThreshold: boolean;
}

interface TimelineViewProps {
  readonly entries: readonly TimelineEntryView[];
  readonly onSeek?: (startMs: number) => void;
  readonly onPlaybackStart?: (measurement: PlaybackStartMeasurement) => void;
  readonly requestPlayback?: (
    entry: TimelineEntryView,
  ) => Promise<PlaybackReferenceView>;
  readonly now?: () => number;
  readonly wallClockNow?: () => number;
}

interface ActivePlayback {
  readonly entry: TimelineEntryView;
  readonly reference: PlaybackReferenceView;
}

export function TimelineView({
  entries,
  onSeek,
  onPlaybackStart,
  requestPlayback,
  now = () => performance.now(),
  wallClockNow = () => new Date().getTime(),
}: TimelineViewProps) {
  const [activePlayback, setActivePlayback] = useState<ActivePlayback | null>(null);
  const [playbackStatus, setPlaybackStatus] = useState<string | null>(null);
  const playbackStartedAt = useRef<number | null>(null);

  async function selectEntry(entry: TimelineEntryView) {
    onSeek?.(entry.startMs);
    if (!entry.evidence || requestPlayback === undefined) return;

    playbackStartedAt.current = now();
    setPlaybackStatus("서명 재생 URL 확인 중");
    try {
      const reference = await requestPlayback(entry);
      const expiresAt = Date.parse(reference.expiresAt);
      if (!reference.url || !Number.isFinite(expiresAt) || expiresAt <= wallClockNow()) {
        throw new Error("invalid playback reference");
      }
      setActivePlayback({ entry, reference });
      setPlaybackStatus("영상 로드 중");
    } catch {
      playbackStartedAt.current = null;
      setActivePlayback(null);
      setPlaybackStatus("재생 URL을 불러오지 못했습니다.");
    }
  }

  async function play(video: HTMLVideoElement) {
    try {
      await video.play();
    } catch {
      playbackStartedAt.current = null;
      setPlaybackStatus("영상 재생을 시작하지 못했습니다.");
    }
  }

  function preparePlayback(video: HTMLVideoElement) {
    if (activePlayback === null) return;
    const targetSeconds = activePlayback.entry.startMs / 1000;
    if (targetSeconds > 0) {
      video.currentTime = targetSeconds;
      return;
    }
    void play(video);
  }

  function recordPlaybackStart(video: HTMLVideoElement) {
    if (activePlayback === null || playbackStartedAt.current === null) return;
    const elapsedMs = Math.round(now() - playbackStartedAt.current);
    const seekOffsetMs = Math.round(
      Math.abs(video.currentTime * 1000 - activePlayback.entry.startMs),
    );
    const measurement = {
      elapsedMs,
      entryId: activePlayback.entry.id,
      seekOffsetMs,
      withinThreshold:
        elapsedMs <= MAXIMUM_PLAYBACK_START_MS &&
        seekOffsetMs <= MAXIMUM_PLAYBACK_START_MS,
    };
    playbackStartedAt.current = null;
    setPlaybackStatus(
      measurement.withinThreshold
        ? `재생 시작: ${measurement.elapsedMs}ms`
        : "재생 시작 2초 기준을 초과했습니다.",
    );
    onPlaybackStart?.(measurement);
  }

  return (
    <section aria-labelledby="timeline-title">
      <h2 id="timeline-title">동기화된 면접 타임라인</h2>
      <input aria-label="타임라인 검색" type="search" />
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <button type="button" onClick={() => void selectEntry(entry)}>
              {entry.text}
            </button>
            {entry.evidence && <span>Evidence</span>}
          </li>
        ))}
      </ul>
      {activePlayback !== null && (
        <video
          aria-label="Evidence 영상"
          controls
          key={`${activePlayback.entry.id}:${activePlayback.reference.url}`}
          onLoadedMetadata={(event) => preparePlayback(event.currentTarget)}
          onPlaying={(event) => recordPlaybackStart(event.currentTarget)}
          onSeeked={(event) => void play(event.currentTarget)}
          preload="auto"
          src={activePlayback.reference.url}
        />
      )}
      {playbackStatus !== null && <output>{playbackStatus}</output>}
    </section>
  );
}
