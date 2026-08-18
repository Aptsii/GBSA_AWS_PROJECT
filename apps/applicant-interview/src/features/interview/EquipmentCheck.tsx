import { useState } from "react";

import { updateApplicantProgress } from "../../app/progress";
import { interviewApi, type InterviewApi } from "./api";

export type ReadinessStatus = "ready" | "warning" | "failed";

export interface EquipmentReadiness {
  readonly camera: ReadinessStatus;
  readonly microphone: ReadinessStatus;
  readonly network: ReadinessStatus;
}

export interface SavedEquipmentReadiness extends EquipmentReadiness {
  readonly equipment_check_id: string;
}

interface EquipmentCheckProps {
  readonly api?: InterviewApi;
  readonly onReady?: (readiness: SavedEquipmentReadiness) => void;
}

const statusLabels: Record<ReadinessStatus, string> = {
  ready: "준비됨",
  warning: "확인 필요",
  failed: "사용 불가",
};

export function EquipmentCheck({
  api = interviewApi,
  onReady,
}: EquipmentCheckProps) {
  const [readiness, setReadiness] = useState<EquipmentReadiness>({
    camera: "warning",
    microphone: "warning",
    network: isOnline() ? "ready" : "failed",
  });
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

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
      network: isOnline() ? "ready" : "failed",
    });
    setChecking(false);
  }

  async function completeCheck() {
    setSaving(true);
    setStatusMessage("");
    setErrorMessage("");
    try {
      const saved = await api.recordEquipmentCheck(readiness);
      updateApplicantProgress({ equipmentCheckId: saved.equipment_check_id });
      setStatusMessage("장비 점검 결과가 API에 저장되었습니다.");
      onReady?.({
        ...readiness,
        equipment_check_id: saved.equipment_check_id,
      });
    } catch {
      setErrorMessage(
        "장비 점검 결과를 저장하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.",
      );
    } finally {
      setSaving(false);
    }
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
        onClick={() => void completeCheck()}
        disabled={!canContinue || saving}
      >
        {saving ? "결과 저장 중" : "장비 점검 완료"}
      </button>
      {statusMessage && <p role="status">{statusMessage}</p>}
      {errorMessage && <p role="alert">{errorMessage}</p>}
    </section>
  );
}

function isOnline(): boolean {
  return typeof navigator === "undefined" || navigator.onLine;
}
