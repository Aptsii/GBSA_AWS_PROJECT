import { createApiClient } from "@interview-evidence/web-client";

const COMPANY_BEARER_KEY = "iep.company.bearer";

export function getCompanyBearer(): string | null {
  return globalThis.localStorage?.getItem(COMPANY_BEARER_KEY) ?? null;
}

export function setCompanyBearer(value: string): void {
  const bearer = value.trim();
  if (bearer) {
    globalThis.localStorage?.setItem(COMPANY_BEARER_KEY, bearer);
  } else {
    globalThis.localStorage?.removeItem(COMPANY_BEARER_KEY);
  }
}

export const apiClient = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "/v1",
  getCompanyBearer,
});
