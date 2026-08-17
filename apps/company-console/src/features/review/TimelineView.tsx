export interface TimelineEntryView {
  readonly id: string;
  readonly text: string;
  readonly startMs: number;
  readonly evidence?: boolean;
}

interface TimelineViewProps {
  readonly entries: readonly TimelineEntryView[];
  readonly onSeek?: (startMs: number) => void;
}

export function TimelineView({ entries, onSeek }: TimelineViewProps) {
  return (
    <section aria-labelledby="timeline-title">
      <h2 id="timeline-title">동기화된 면접 타임라인</h2>
      <input aria-label="타임라인 검색" type="search" />
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <button type="button" onClick={() => onSeek?.(entry.startMs)}>
              {entry.text}
            </button>
            {entry.evidence && <span>Evidence</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
