export interface ApplicantProgress {
  readonly acknowledgedPartialAnalysis?: boolean;
  readonly equipmentCheckId?: string;
  readonly interviewSessionId?: string;
  readonly strategyId?: string;
  readonly websocketPath?: string;
}

const STORAGE_KEY = "iep.applicant.progress";

export function getApplicantProgress(): ApplicantProgress {
  try {
    const value = globalThis.sessionStorage?.getItem(STORAGE_KEY);
    return value ? (JSON.parse(value) as ApplicantProgress) : {};
  } catch {
    return {};
  }
}

export function updateApplicantProgress(
  update: Partial<ApplicantProgress>,
): ApplicantProgress {
  const next = { ...getApplicantProgress(), ...update };
  globalThis.sessionStorage?.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function clearApplicantProgress(): void {
  globalThis.sessionStorage?.removeItem(STORAGE_KEY);
}
