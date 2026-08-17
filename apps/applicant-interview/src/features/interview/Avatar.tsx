import { useEffect, useState } from "react";

export interface AvatarSpeechMark {
  readonly offsetMs: number;
  readonly value: string;
}

interface AvatarProps {
  readonly speaking: boolean;
  readonly textOnly?: boolean;
  readonly speechMarks?: readonly AvatarSpeechMark[];
}

export function Avatar({
  speaking,
  textOnly = false,
  speechMarks = [],
}: AvatarProps) {
  const [activeMark, setActiveMark] = useState("rest");

  useEffect(() => {
    if (!speaking || textOnly) return;
    const timers = [
      window.setTimeout(() => setActiveMark("rest"), 0),
      ...speechMarks.map((mark) =>
        window.setTimeout(() => setActiveMark(mark.value), mark.offsetMs),
      ),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [speaking, speechMarks, textOnly]);

  const displayedMark = speaking && !textOnly ? activeMark : "rest";

  return (
    <figure
      aria-label="AI 면접 진행자 아바타"
      data-speaking={speaking && !textOnly}
      data-speech-mark={displayedMark}
    >
      <svg viewBox="0 0 160 160" role="img" aria-hidden="true">
        <circle cx="80" cy="80" r="72" fill="#e8eef9" />
        <circle cx="57" cy="66" r="6" fill="#24324a" />
        <circle cx="103" cy="66" r="6" fill="#24324a" />
        <ellipse
          cx="80"
          cy="105"
          rx={displayedMark === "rest" ? 18 : 12}
          ry={displayedMark === "rest" ? 4 : 12}
          fill="#6b3f4f"
        />
      </svg>
      <figcaption>
        {textOnly
          ? "텍스트 질문 모드"
          : speaking
            ? "질문 음성 재생 중"
            : "대기 중"}
      </figcaption>
    </figure>
  );
}
