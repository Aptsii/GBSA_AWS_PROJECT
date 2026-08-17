import { useState } from "react";

export type ReadinessStatus = "ready" | "warning" | "failed";

export interface EquipmentReadiness {
  readonly camera: ReadinessStatus;
  readonly microphone: ReadinessStatus;
  readonly network: ReadinessStatus;
}

interface EquipmentCheckProps {
  readonly onReady?: (readiness: EquipmentReadiness) => void;
}

const statusLabels: Record<ReadinessStatus, string> = {
  ready: "준비됨",
  warning: "확인 필요",
  failed: "사용 불가",
};

export function EquipmentCheck({ onReady }: EquipmentCheckProps) {
  const [readiness, setReadiness] = useState<EquipmentReadiness>({
    camera: "warning",
    microphone: "warning",
    network: navigator.onLine ? "ready" : "failed",
  });
  const [checking, setChecking] = useState(false);

  async function runCheck() {
    setChecking(true);
    let camera: ReadinessStatus = "warning";
    let microphone: ReadinessStatus = "warning";
    try {
      const stream = await navigator.mediaDevices?.getUserMedia({
        audio: true,
        video: true,
      });
      if (stream) {
        camera = stream.getVideoTracks().length ? "ready" : "failed";
        microphone = stream.getAudioTracks().length ? "ready" : "failed";
        stream.getTracks().forEach((track) => track.stop());
      }
    } catch {
      camera = "failed";
      microphone = "failed";
    }
    setReadiness({
      camera,
      microphone,
      network: navigator.onLine ? "ready" : "failed",
    });
    setChecking(false);
  }

  const canContinue = Object.values(readiness).every(
    (status) => status !== "failed",
  );

  return (
    <section aria-labelledby="equipment-check-title">
      <p>면접 시작 전 확인</p>
      <h1 id="equipment-check-title">장비 및 네트워크 점검</h1>
      <p>
        카메라와 마이크 권한은 면접 진행에만 사용됩니다. 점검 결과는 평가에
        반영되지 않습니다.
      </p>

      <dl>
        <div>
          <dt>카메라</dt>
          <dd>{statusLabels[readiness.camera]}</dd>
        </div>
        <div>
          <dt>마이크</dt>
          <dd>{statusLabels[readiness.microphone]}</dd>
        </div>
        <div>
          <dt>네트워크</dt>
          <dd>{statusLabels[readiness.network]}</dd>
        </div>
      </dl>

      <button type="button" onClick={runCheck} disabled={checking}>
        {checking ? "점검 중" : "장비 다시 점검"}
      </button>
      <button
        type="button"
        onClick={() => onReady?.(readiness)}
        disabled={!canContinue}
      >
        장비 점검 완료
      </button>
    </section>
  );
}
