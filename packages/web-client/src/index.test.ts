import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiProblem,
  createApiClient,
  createIdempotencyKey,
  createUuid7,
  createWebSocketUrl,
} from "./index";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("browser API client", () => {
  it("adds company bearer, request identity and idempotency headers", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ position_id: "position-1" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({
      baseUrl: "http://localhost:8001/v1/",
      getCompanyBearer: () => "company-token",
    });

    await client.post(
      "/positions",
      { title: "백엔드 개발자" },
      { auth: "company" },
    );

    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8001/v1/positions");
    expect(request?.credentials).toBe("include");
    const headers = new Headers(request?.headers);
    expect(headers.get("authorization")).toBe("Bearer company-token");
    expect(headers.get("idempotency-key")).toMatch(/^[A-Za-z0-9_.:-]{16,128}$/);
    expect(headers.get("x-request-id")).toBeTruthy();
  });

  it("uses the applicant cookie without exposing a bearer token", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: "ready" }), {
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ baseUrl: "/v1" });

    await client.get("/applicant/analysis-status", { auth: "applicant" });

    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.has("authorization")).toBe(false);
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe("include");
  });

  it("returns undefined for a successful empty response", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status: 204 })),
    );
    const client = createApiClient({ baseUrl: "/v1" });

    await expect(
      client.post("/applicant/access/exchange", { invitation_token: "token" }),
    ).resolves.toBeUndefined();
  });

  it("raises a safe typed problem without leaking an HTML response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "about:blank",
            title: "요청을 처리할 수 없습니다.",
            status: 409,
            code: "STALE_VERSION",
            request_id: "0198b6c5-8800-7000-8000-000000000001",
            retryable: true,
          }),
          {
            status: 409,
            headers: { "content-type": "application/problem+json" },
          },
        ),
      ),
    );
    const client = createApiClient({ baseUrl: "/v1" });

    await expect(client.get("/positions", { auth: "company" })).rejects.toEqual(
      expect.objectContaining({
        code: "STALE_VERSION",
        status: 409,
        retryable: true,
      } satisfies Partial<ApiProblem>),
    );
  });

  it("creates protocol-safe idempotency keys and websocket URLs", () => {
    expect(createIdempotencyKey("position")).toMatch(
      /^position:[A-Za-z0-9-]+$/,
    );
    expect(createUuid7()).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(
      createWebSocketUrl(
        "https://app.example.com/v1",
        "/applicant/interview-sessions/s1/stream",
      ),
    ).toBe("wss://app.example.com/v1/applicant/interview-sessions/s1/stream");
  });
});
