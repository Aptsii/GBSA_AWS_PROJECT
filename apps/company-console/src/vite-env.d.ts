/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_COMPANY_IDENTITY_CLIENT_ID?: string;
  readonly VITE_COMPANY_IDENTITY_ENDPOINT?: string;
  readonly VITE_COMPANY_IDENTITY_MODE?: "cognito" | "local";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
