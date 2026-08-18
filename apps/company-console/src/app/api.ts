import { createApiClient } from "@interview-evidence/web-client";

import { createCompanyIdentitySession } from "../features/company/identity";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/v1";
const identityMode = import.meta.env.VITE_COMPANY_IDENTITY_MODE ?? "local";

export const companyIdentitySession = createCompanyIdentitySession({
  apiBaseUrl,
  clientId: import.meta.env.VITE_COMPANY_IDENTITY_CLIENT_ID,
  identityEndpoint: import.meta.env.VITE_COMPANY_IDENTITY_ENDPOINT,
  mode: identityMode === "cognito" ? "cognito" : "local",
});

export const apiClient = createApiClient({
  baseUrl: apiBaseUrl,
  getCompanyBearer: () => companyIdentitySession.getBearer(),
});
