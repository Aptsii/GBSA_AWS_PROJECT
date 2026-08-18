import { createApiClient } from "@interview-evidence/web-client";

export const apiClient = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "/v1",
});

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/v1";
