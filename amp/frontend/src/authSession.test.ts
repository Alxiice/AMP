import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthStatus } from "./api";
import { refreshAuthStatus, sessionLabel } from "./authSession";

const status = (state: AuthStatus["state"]): AuthStatus => ({
  state,
  is_authenticated: state === "signed_in",
  account: null,
});

describe("sessionLabel", () => {
  it("names each state", () => {
    expect(sessionLabel(status("signed_in"))).toBe("Signed in");
    expect(sessionLabel(status("signed_out"))).toBe("Signed out");
    expect(sessionLabel(status("expired"))).toBe("Session expired — reconnect");
    expect(sessionLabel(null)).toBe("Session: unknown");
  });
});

describe("401 from /api/user/*", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("refreshes the session status", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push(url);
      if (url.includes("/api/user/")) return new Response('{"detail":"Not signed in"}', { status: 401 });
      return new Response(JSON.stringify(status("expired")), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }));

    const { api } = await import("./api");
    await expect(api.getUserLikes()).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(calls.some((u) => u.includes("/api/auth/status"))).toBe(true));
    expect((await refreshAuthStatus())?.state).toBe("expired");
  });
});
