import { createRoot } from "react-dom/client";

import {
  PlaybackReferenceView,
  PlaybackStartMeasurement,
  TimelineEntryView,
  TimelineView,
} from "../TimelineView";

const entry: TimelineEntryView = {
  id: "browser-evidence-001",
  text: "브라우저 Evidence 재생",
  startMs: 200,
  evidence: true,
};

function decodeWebm(encoded: string) {
  const binary = atob(encoded.trim());
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: "video/webm" });
}

async function requestPlayback(
  selected: TimelineEntryView,
): Promise<PlaybackReferenceView> {
  const signedUrl = new URL(
    "./fixtures/evidence-playback.webm.b64?signature=synthetic-browser-evidence",
    import.meta.url,
  );
  signedUrl.searchParams.set("entry_id", selected.id);
  try {
    const response = await fetch(signedUrl);
    if (!response.ok || !response.url.includes("signature=")) {
      throw new Error("signed playback retrieval failed");
    }
    document.body.dataset.signedPlaybackRetrieved = "true";
    const media = decodeWebm(await response.text());
    return {
      url: URL.createObjectURL(media),
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    };
  } catch (error) {
    document.body.dataset.status = "failed";
    document.body.dataset.error =
      error instanceof Error
        ? error.message
        : "unknown playback retrieval error";
    throw error;
  }
}

function recordMeasurement(measurement: PlaybackStartMeasurement) {
  document.body.dataset.status = measurement.withinThreshold
    ? "passed"
    : "failed";
  document.body.dataset.elapsedMs = String(measurement.elapsedMs);
  document.body.dataset.seekOffsetMs = String(measurement.seekOffsetMs);
}

createRoot(document.querySelector("#root")!).render(
  <TimelineView
    entries={[entry]}
    onPlaybackStart={recordMeasurement}
    requestPlayback={requestPlayback}
  />,
);
