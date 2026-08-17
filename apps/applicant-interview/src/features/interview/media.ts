export interface RecordingChunkPayload {
  readonly sessionId: string;
  readonly sequence: number;
  readonly blob: Blob;
  readonly byteSize: number;
  readonly sha256: string;
  readonly startMs: number;
  readonly endMs: number;
}

interface StoredChunk extends RecordingChunkPayload {
  readonly id: string;
}

export class LocalRetryBuffer {
  private readonly memory = new Map<string, StoredChunk>();
  private databasePromise?: Promise<IDBDatabase>;

  async put(chunk: RecordingChunkPayload): Promise<void> {
    const stored = { ...chunk, id: chunkId(chunk.sessionId, chunk.sequence) };
    this.memory.set(stored.id, stored);
    const database = await this.database();
    if (!database) return;
    await requestDone(
      database
        .transaction("recordingChunks", "readwrite")
        .objectStore("recordingChunks")
        .put(stored),
    );
  }

  async pending(sessionId: string): Promise<readonly RecordingChunkPayload[]> {
    const database = await this.database();
    if (database) {
      const rows = await requestDone<StoredChunk[]>(
        database
          .transaction("recordingChunks", "readonly")
          .objectStore("recordingChunks")
          .getAll(),
      );
      rows.forEach((row) => this.memory.set(row.id, row));
    }
    return [...this.memory.values()]
      .filter((chunk) => chunk.sessionId === sessionId)
      .sort((left, right) => left.sequence - right.sequence)
      .map((chunk) => ({
        sessionId: chunk.sessionId,
        sequence: chunk.sequence,
        blob: chunk.blob,
        byteSize: chunk.byteSize,
        sha256: chunk.sha256,
        startMs: chunk.startMs,
        endMs: chunk.endMs,
      }));
  }

  async remove(sessionId: string, sequence: number): Promise<void> {
    const id = chunkId(sessionId, sequence);
    this.memory.delete(id);
    const database = await this.database();
    if (!database) return;
    await requestDone(
      database
        .transaction("recordingChunks", "readwrite")
        .objectStore("recordingChunks")
        .delete(id),
    );
  }

  private async database(): Promise<IDBDatabase | undefined> {
    if (typeof indexedDB === "undefined") return undefined;
    this.databasePromise ??= new Promise((resolve, reject) => {
      const request = indexedDB.open("iep-interview-media", 1);
      request.addEventListener("upgradeneeded", () => {
        if (!request.result.objectStoreNames.contains("recordingChunks")) {
          request.result.createObjectStore("recordingChunks", {
            keyPath: "id",
          });
        }
      });
      request.addEventListener("success", () => resolve(request.result));
      request.addEventListener("error", () => reject(request.error));
    });
    return this.databasePromise;
  }
}

export class ChunkedRecorder {
  private readonly recorder: MediaRecorder;
  private sequence = 0;
  private chunkStartMs = 0;

  constructor(
    stream: MediaStream,
    private readonly sessionId: string,
    private readonly upload: (chunk: RecordingChunkPayload) => Promise<void>,
    private readonly retryBuffer = new LocalRetryBuffer(),
  ) {
    const preferredMimeType = MediaRecorder.isTypeSupported(
      "video/webm;codecs=vp9,opus",
    )
      ? "video/webm;codecs=vp9,opus"
      : "video/webm";
    this.recorder = new MediaRecorder(stream, { mimeType: preferredMimeType });
    this.recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) void this.handleChunk(event.data);
    });
  }

  start(timesliceMs = 2_000): void {
    if (timesliceMs < 500) throw new Error("녹화 청크 간격이 너무 짧습니다.");
    this.chunkStartMs = performance.now();
    this.recorder.start(timesliceMs);
  }

  stop(): Promise<void> {
    if (this.recorder.state === "inactive") return Promise.resolve();
    return new Promise((resolve) => {
      this.recorder.addEventListener("stop", () => resolve(), { once: true });
      this.recorder.stop();
    });
  }

  async retryPending(): Promise<void> {
    for (const chunk of await this.retryBuffer.pending(this.sessionId)) {
      await this.upload(chunk);
      await this.retryBuffer.remove(chunk.sessionId, chunk.sequence);
      this.sequence = Math.max(this.sequence, chunk.sequence);
    }
  }

  private async handleChunk(blob: Blob): Promise<void> {
    const endMs = performance.now();
    const sequence = this.sequence + 1;
    const bytes = await blob.arrayBuffer();
    const chunk: RecordingChunkPayload = {
      sessionId: this.sessionId,
      sequence,
      blob,
      byteSize: blob.size,
      sha256: await digest(bytes),
      startMs: Math.round(this.chunkStartMs),
      endMs: Math.round(endMs),
    };
    this.chunkStartMs = endMs;
    this.sequence = sequence;
    await this.retryBuffer.put(chunk);
    try {
      await this.upload(chunk);
      await this.retryBuffer.remove(chunk.sessionId, chunk.sequence);
    } catch {
      // The buffered chunk is retried after reconnect; applicant media is not logged.
    }
  }
}

export async function connectAudioWorklet(
  context: AudioContext,
  moduleUrl: string,
  processorName: string,
): Promise<AudioWorkletNode> {
  await context.audioWorklet.addModule(moduleUrl);
  const node = new AudioWorkletNode(context, processorName);
  node.connect(context.destination);
  return node;
}

async function digest(bytes: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function chunkId(sessionId: string, sequence: number): string {
  return `${sessionId}:${sequence}`;
}

function requestDone<Result>(request: IDBRequest<Result>): Promise<Result> {
  return new Promise((resolve, reject) => {
    request.addEventListener("success", () => resolve(request.result));
    request.addEventListener("error", () => reject(request.error));
  });
}
