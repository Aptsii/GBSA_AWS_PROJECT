const STORAGE_KEY = "iep.company.identity-session";
const EXPIRY_MARGIN_MS = 30_000;

export interface CompanyIdentitySession {
  getBearer(): Promise<string | null>;
  hasSession(): boolean;
  signIn(email: string, password: string): Promise<void>;
  signOut(): void;
}

interface CompanyIdentitySessionOptions {
  readonly apiBaseUrl?: string;
  readonly clientId?: string;
  readonly fetchImplementation?: typeof fetch;
  readonly identityEndpoint?: string;
  readonly mode: "cognito" | "local";
  readonly now?: () => number;
  readonly storage?: Storage;
}

interface StoredIdentitySession {
  readonly accessToken: string;
  readonly expiresAt: number;
  readonly refreshToken?: string;
}

interface CognitoAuthenticationResult {
  readonly ExpiresIn?: number;
  readonly IdToken?: string;
  readonly RefreshToken?: string;
}

interface CognitoResponse {
  readonly AuthenticationResult?: CognitoAuthenticationResult;
}

interface LocalSessionResponse {
  readonly access_token?: string;
  readonly expires_at?: string;
}

export function createCompanyIdentitySession(
  options: CompanyIdentitySessionOptions,
): CompanyIdentitySession {
  const requestFetch = options.fetchImplementation ?? fetch;
  const storage = options.storage ?? globalThis.sessionStorage;
  const now = options.now ?? Date.now;

  function read(): StoredIdentitySession | null {
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      const value = JSON.parse(raw) as Partial<StoredIdentitySession>;
      if (
        typeof value.accessToken !== "string" ||
        typeof value.expiresAt !== "number" ||
        (value.refreshToken !== undefined &&
          typeof value.refreshToken !== "string")
      ) {
        throw new TypeError("invalid identity session");
      }
      return value as StoredIdentitySession;
    } catch {
      storage?.removeItem(STORAGE_KEY);
      return null;
    }
  }

  function save(value: StoredIdentitySession): void {
    storage?.setItem(STORAGE_KEY, JSON.stringify(value));
  }

  async function cognitoRequest(
    authFlow: "REFRESH_TOKEN_AUTH" | "USER_PASSWORD_AUTH",
    authParameters: Record<string, string>,
  ): Promise<CognitoAuthenticationResult> {
    if (!options.identityEndpoint || !options.clientId) {
      throw new Error("기업 인증 환경이 구성되지 않았습니다.");
    }
    const response = await requestFetch(options.identityEndpoint, {
      body: JSON.stringify({
        AuthFlow: authFlow,
        AuthParameters: authParameters,
        ClientId: options.clientId,
      }),
      headers: {
        "content-type": "application/x-amz-json-1.1",
        "x-amz-target": "AWSCognitoIdentityProviderService.InitiateAuth",
      },
      method: "POST",
    });
    if (!response.ok) {
      throw new Error("이메일 또는 비밀번호를 확인해 주세요.");
    }
    const payload = (await response.json()) as CognitoResponse;
    const result = payload.AuthenticationResult;
    if (!result?.IdToken || !result.ExpiresIn) {
      throw new Error("기업 인증 세션을 시작할 수 없습니다.");
    }
    return result;
  }

  async function localSignIn(email: string, password: string): Promise<void> {
    const baseUrl = (options.apiBaseUrl ?? "/v1").replace(/\/+$/, "");
    const response = await requestFetch(`${baseUrl}/local/company-sessions`, {
      body: JSON.stringify({ email, password }),
      headers: { "content-type": "application/json" },
      method: "POST",
    });
    if (!response.ok) {
      throw new Error("이메일 또는 비밀번호를 확인해 주세요.");
    }
    const payload = (await response.json()) as LocalSessionResponse;
    const expiresAt = Date.parse(payload.expires_at ?? "");
    if (!payload.access_token || !Number.isFinite(expiresAt)) {
      throw new Error("로컬 기업 인증 세션을 시작할 수 없습니다.");
    }
    save({ accessToken: payload.access_token, expiresAt });
  }

  return {
    async getBearer() {
      const current = read();
      if (!current) return null;
      if (current.expiresAt - now() > EXPIRY_MARGIN_MS) {
        return current.accessToken;
      }
      if (options.mode !== "cognito" || !current.refreshToken) {
        storage?.removeItem(STORAGE_KEY);
        return null;
      }
      const refreshed = await cognitoRequest("REFRESH_TOKEN_AUTH", {
        REFRESH_TOKEN: current.refreshToken,
      });
      const next = {
        accessToken: refreshed.IdToken as string,
        expiresAt: now() + (refreshed.ExpiresIn as number) * 1_000,
        refreshToken: current.refreshToken,
      };
      save(next);
      return next.accessToken;
    },
    hasSession() {
      return read() !== null;
    },
    async signIn(email, password) {
      const normalizedEmail = email.trim().toLowerCase();
      if (!normalizedEmail || !password) {
        throw new Error("이메일과 비밀번호를 입력해 주세요.");
      }
      if (options.mode === "local") {
        await localSignIn(normalizedEmail, password);
        return;
      }
      const authenticated = await cognitoRequest("USER_PASSWORD_AUTH", {
        PASSWORD: password,
        USERNAME: normalizedEmail,
      });
      save({
        accessToken: authenticated.IdToken as string,
        expiresAt: now() + (authenticated.ExpiresIn as number) * 1_000,
        refreshToken: authenticated.RefreshToken,
      });
    },
    signOut() {
      storage?.removeItem(STORAGE_KEY);
    },
  };
}
