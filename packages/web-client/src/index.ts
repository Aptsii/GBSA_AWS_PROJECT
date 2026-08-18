import type { ErrorEnvelope } from "@interview-evidence/contracts";

export type ApiAuth = "none" | "company" | "applicant";

export interface ApiClientOptions {
  readonly baseUrl: string;
  readonly getCompanyBearer?: () =>
    string | null | undefined | Promise<string | null | undefined>;
  readonly fetchImplementation?: typeof fetch;
}

export interface ApiRequestOptions {
  readonly auth?: ApiAuth;
  readonly headers?: HeadersInit;
  readonly idempotencyKey?: string;
  readonly signal?: AbortSignal;
}

export interface UploadOptions {
  readonly contentType: string;
  readonly headers?: HeadersInit;
  readonly signal?: AbortSignal;
}

export class ApiProblem extends Error {
  readonly code: string;
  readonly detail?: string;
  readonly fields: ReadonlyArray<{
    readonly field: string;
    readonly code: string;
  }>;
  readonly requestId?: string;
  readonly retryable: boolean;
  readonly status: number;

  constructor(
    problem: Partial<ErrorEnvelope> &
      Pick<ErrorEnvelope, "status" | "code" | "title">,
  ) {
    super(problem.title);
    this.name = "ApiProblem";
    this.code = problem.code;
    this.detail = problem.detail;
    this.fields = problem.errors ?? [];
    this.requestId = problem.request_id;
    this.retryable = problem.retryable ?? false;
    this.status = problem.status;
  }
}

export interface BrowserApiClient {
  get<T>(path: string, options?: ApiRequestOptions): Promise<T>;
  post<T, Body = unknown>(
    path: string,
    body: Body,
    options?: ApiRequestOptions,
  ): Promise<T>;
  put<T, Body = unknown>(
    path: string,
    body: Body,
    options?: ApiRequestOptions,
  ): Promise<T>;
  upload(url: string, body: BodyInit, options: UploadOptions): Promise<void>;
}

export function createApiClient(options: ApiClientOptions): BrowserApiClient {
  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const requestFetch = options.fetchImplementation ?? fetch;

  async function request<T>(
    method: "GET" | "POST" | "PUT",
    path: string,
    body: unknown,
    requestOptions: ApiRequestOptions = {},
  ): Promise<T> {
    const headers = new Headers(requestOptions.headers);
    headers.set("accept", "application/json, application/problem+json");
    headers.set("x-request-id", crypto.randomUUID());

    if (requestOptions.auth === "company") {
      const bearer = await options.getCompanyBearer?.();
      if (bearer) headers.set("authorization", `Bearer ${bearer}`);
    }
    if (method !== "GET") {
      headers.set(
        "idempotency-key",
        requestOptions.idempotencyKey ??
          createIdempotencyKey(method.toLowerCase()),
      );
    }

    let encodedBody: BodyInit | undefined;
    if (body !== undefined) {
      headers.set("content-type", "application/json");
      encodedBody = JSON.stringify(body);
    }

    const response = await requestFetch(joinUrl(baseUrl, path), {
      body: encodedBody,
      credentials: "include",
      headers,
      method,
      signal: requestOptions.signal,
    });
    if (!response.ok) throw await parseProblem(response);
    if (response.status === 204) return undefined as T;
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("json")) return undefined as T;
    return (await response.json()) as T;
  }

  return {
    get: <T>(path: string, requestOptions?: ApiRequestOptions) =>
      request<T>("GET", path, undefined, requestOptions),
    post: <T, Body = unknown>(
      path: string,
      body: Body,
      requestOptions?: ApiRequestOptions,
    ) => request<T>("POST", path, body, requestOptions),
    put: <T, Body = unknown>(
      path: string,
      body: Body,
      requestOptions?: ApiRequestOptions,
    ) => request<T>("PUT", path, body, requestOptions),
    async upload(
      url: string,
      body: BodyInit,
      uploadOptions: UploadOptions,
    ): Promise<void> {
      const headers = new Headers(uploadOptions.headers);
      headers.set("content-type", uploadOptions.contentType);
      const response = await requestFetch(url, {
        body,
        credentials: "omit",
        headers,
        method: "PUT",
        signal: uploadOptions.signal,
      });
      if (!response.ok) throw await parseProblem(response);
    },
  };
}

export function createIdempotencyKey(scope = "web"): string {
  const safeScope =
    scope.replace(/[^A-Za-z0-9_.:-]/g, "-").slice(0, 32) || "web";
  return `${safeScope}:${crypto.randomUUID()}`;
}

export function createUuid7(now = Date.now()): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let timestamp = BigInt(now);
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = Number(timestamp & 0xffn);
    timestamp >>= 8n;
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x70;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex
    .slice(6, 8)
    .join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

export function createWebSocketUrl(
  baseUrl: string,
  path: string,
  origin?: string,
): string {
  const browserOrigin = origin ?? globalThis.location?.origin;
  const resolved = new URL(
    joinUrl(normalizeBaseUrl(baseUrl), path),
    browserOrigin,
  );
  resolved.protocol = resolved.protocol === "https:" ? "wss:" : "ws:";
  return resolved.toString();
}

async function parseProblem(response: Response): Promise<ApiProblem> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("json")) {
    try {
      const candidate = (await response.json()) as Partial<ErrorEnvelope>;
      if (
        typeof candidate.title === "string" &&
        typeof candidate.code === "string" &&
        typeof candidate.status === "number"
      ) {
        return new ApiProblem({
          ...candidate,
          status: candidate.status,
          code: candidate.code,
          title: candidate.title,
        });
      }
    } catch {
      // Fall through to the bounded generic error below.
    }
  }
  return new ApiProblem({
    code: `HTTP_${response.status}`,
    retryable: response.status >= 500,
    status: response.status,
    title: "요청을 처리할 수 없습니다.",
  });
}

function normalizeBaseUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "/v1";
  return trimmed.replace(/\/+$/, "");
}

function joinUrl(baseUrl: string, path: string): string {
  return `${baseUrl}/${path.replace(/^\/+/, "")}`;
}
