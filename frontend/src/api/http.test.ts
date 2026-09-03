/** The session client. Design section 8; the acceptance bar for step 9.
 *
 * The thing worth testing here is not that a 401 gets refreshed -- that is four
 * lines -- but that N requests failing at once produce one refresh. Get it
 * wrong and the app rotates the refresh token five times in a tick; four of
 * those spend a token a sibling already replaced, which is exactly the shape of
 * a replayed stolen token, and step 14's reuse detection kills the family. The
 * user is logged out for the crime of having five panels on screen.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const CSRF_COOKIE = "__Host-pds_csrf";

interface Call {
  url: string;
  init: RequestInit | undefined;
}

/** A fetch that fails with 401 until a refresh happens, then succeeds.
 *
 * Stands in for a server whose access cookie has aged out: the refresh is what
 * replaces it, and every request after that one is fine.
 */
function server() {
  const calls: Call[] = [];
  let accessValid = false;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url === "/api/auth/refresh") {
      accessValid = true;
      return new Response("{}", { status: 200 });
    }
    if (!accessValid) return new Response(JSON.stringify({ error: { message: "로그인이 필요합니다." } }), { status: 401 });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  });
  return {
    calls,
    fetchMock,
    refreshes: () => calls.filter((call) => call.url === "/api/auth/refresh").length,
    expire: () => {
      accessValid = false;
    },
  };
}

async function loadClient() {
  vi.resetModules();
  return import("./http");
}

beforeEach(() => {
  // Path and Secure are what the `__Host-` prefix requires; without them the
  // cookie jar refuses the name.
  document.cookie = `${CSRF_COOKIE}=synthetic-csrf-value; path=/; secure`;
});

afterEach(() => {
  document.cookie = `${CSRF_COOKIE}=; path=/; secure; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
});

describe("recovering from an expired access token", () => {
  it("refreshes once for five requests that fail together", async () => {
    const api = server();
    vi.stubGlobal("fetch", api.fetchMock);
    const { request } = await loadClient();

    const results = await Promise.all(
      ["/api/plans", "/api/tasks", "/api/export", "/api/auth/me", "/api/plans/x/see"].map((url) =>
        request<{ ok: boolean }>(url),
      ),
    );

    expect(results).toHaveLength(5);
    expect(api.refreshes()).toBe(1);
  });

  it("retries the original request rather than refreshing, if a peer got there first", async () => {
    // The second caller into the critical section must re-check before spending
    // a rotation. Proven by counting: five callers, five first attempts, one
    // refresh, and the four re-checks that made the refresh unnecessary.
    const api = server();
    vi.stubGlobal("fetch", api.fetchMock);
    const { request } = await loadClient();

    await Promise.all(["/api/a", "/api/b", "/api/c", "/api/d", "/api/e"].map((url) => request(url)));

    const attempts = api.calls.filter((call) => call.url !== "/api/auth/refresh");
    // 5 that failed, 5 re-checks inside the lock, 1 retry after the refresh.
    expect(attempts).toHaveLength(11);
    expect(api.refreshes()).toBe(1);
  });

  it("does not try to refresh the refresh call", async () => {
    // Without the guard this recurses until the stack gives out.
    const fetchMock = vi.fn(async () => new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    const { sendWithSession } = await loadClient();

    const response = await sendWithSession("/api/auth/refresh", { method: "POST", body: "{}" });

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reports a session it could not recover", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    const { onSessionLost, sendWithSession } = await loadClient();
    const lost = vi.fn();
    onSessionLost(lost);

    await sendWithSession("/api/plans");

    // The route gate turns this into a redirect. Without it the user sits on a
    // screen they are no longer allowed to see, reading error messages.
    expect(lost).toHaveBeenCalledTimes(1);
  });

  it("stays silent when the request succeeded after a refresh", async () => {
    const api = server();
    vi.stubGlobal("fetch", api.fetchMock);
    const { onSessionLost, request } = await loadClient();
    const lost = vi.fn();
    onSessionLost(lost);

    await request("/api/plans");

    expect(lost).not.toHaveBeenCalled();
  });
});

describe("two tabs", () => {
  /** A Web Lock manager shared by both module instances, as the browser's is. */
  function sharedLocks() {
    let held: Promise<unknown> = Promise.resolve();
    return {
      request: (_name: string, work: () => Promise<unknown>) => {
        const run = held.then(work, work);
        held = run.then(
          () => undefined,
          () => undefined,
        );
        return run;
      },
    };
  }

  it("refreshes once across two tabs holding the same lock", async () => {
    // Two module instances, one fetch, one lock manager: the parts a second tab
    // shares with the first. Without the lock both tabs rotate, and the loser's
    // rotation is indistinguishable from a replay.
    const api = server();
    vi.stubGlobal("fetch", api.fetchMock);
    vi.stubGlobal("navigator", { ...globalThis.navigator, locks: sharedLocks() });

    const tabOne = await loadClient();
    const tabTwo = await loadClient();

    await Promise.all([tabOne.request("/api/plans"), tabTwo.request("/api/tasks")]);

    expect(api.refreshes()).toBe(1);
  });
});

describe("CSRF", () => {
  it("echoes the readable cookie on a state-changing request", async () => {
    const api = server();
    vi.stubGlobal("fetch", api.fetchMock);
    const { request } = await loadClient();

    await request("/api/plans", { method: "POST", body: "{}" }).catch(() => undefined);

    const headers = api.calls[0].init?.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("synthetic-csrf-value");
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("sends no token on a read", async () => {
    // A header the server does not look at invites someone to believe it
    // matters, and then to move the check to it.
    const api = server();
    vi.stubGlobal("fetch", api.fetchMock);
    const { request } = await loadClient();

    await request("/api/plans").catch(() => undefined);

    expect((api.calls[0].init?.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });

  it("sends the session cookies with every request", async () => {
    const api = server();
    vi.stubGlobal("fetch", api.fetchMock);
    const { request } = await loadClient();

    await request("/api/plans").catch(() => undefined);

    expect(api.calls[0].init?.credentials).toBe("same-origin");
  });
});

describe("errors", () => {
  it("prefers the field detail over the summary message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ error: { message: "계정을 만들 수 없습니다.", details: { email: "이미 가입된 이메일입니다." } } }),
          { status: 409 },
        ),
      ),
    );
    const { ApiError, request } = await loadClient();

    await expect(request("/api/auth/signup", { method: "POST", body: "{}" })).rejects.toMatchObject({
      message: "이미 가입된 이메일입니다.",
      status: 409,
    });
    await expect(request("/api/auth/signup", { method: "POST", body: "{}" })).rejects.toBeInstanceOf(ApiError);
  });

  it("survives a refusal with no JSON body", async () => {
    // A 502 from the platform is HTML. Parsing it must not become a
    // SyntaxError the caller cannot tell apart from a real failure.
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502 })));
    const { request } = await loadClient();

    await expect(request("/api/plans")).rejects.toMatchObject({ status: 502 });
  });
});
