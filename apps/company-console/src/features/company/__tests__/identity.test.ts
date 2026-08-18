import { afterEach, describe, expect, it, vi } from "vitest";

import { createCompanyIdentitySession } from "../identity";

afterEach(() => {
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("company identity session", () => {
  it("exchanges email and password through the isolated local fixture without persisting the password", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "local-company-token",
          expires_at: "2026-08-18T12:00:00Z",
        }),
        { headers: { "content-type": "application/json" } },
      ),
    );
    const session = createCompanyIdentitySession({
      apiBaseUrl: "/v1",
      fetchImplementation: fetchMock,
      mode: "local",
      now: () => new Date("2026-08-18T10:00:00Z").getTime(),
      storage: sessionStorage,
    });

    await session.signIn("owner@example.test", "local-password");

    expect(await session.getBearer()).toBe("local-company-token");
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/local/company-sessions",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.stringify(sessionStorage)).not.toContain("local-password");
  });

  it("refreshes an expiring Cognito identity session before returning its bearer", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            AuthenticationResult: {
              ExpiresIn: 60,
              IdToken: "initial-id-token",
              RefreshToken: "refresh-token",
            },
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            AuthenticationResult: {
              ExpiresIn: 900,
              IdToken: "refreshed-id-token",
            },
          }),
        ),
      );
    let now = new Date("2026-08-18T10:00:00Z").getTime();
    const session = createCompanyIdentitySession({
      clientId: "company-console-client",
      fetchImplementation: fetchMock,
      identityEndpoint: "https://cognito-idp.ap-northeast-2.amazonaws.com/",
      mode: "cognito",
      now: () => now,
      storage: sessionStorage,
    });

    await session.signIn("owner@example.test", "ValidPassword!123");
    now += 45_000;

    expect(await session.getBearer()).toBe("refreshed-id-token");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://cognito-idp.ap-northeast-2.amazonaws.com/",
      expect.objectContaining({
        body: expect.stringContaining("REFRESH_TOKEN_AUTH"),
        method: "POST",
      }),
    );
  });
});
