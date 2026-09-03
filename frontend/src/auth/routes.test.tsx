/** The route gate. T07-C03 and C97.
 *
 * C03 wants /login and /signup reachable with no account; C97 wants /app not to
 * be. Both are about what a person sees, so they are tested through what gets
 * rendered rather than by calling the gate's internals.
 *
 * The diary itself is replaced by a marker here. Whether App renders is a
 * different question from whether it is allowed to, and mounting the real one
 * would drag every panel's data fetching into a test about a redirect.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CredentialsPage from "./CredentialsPage";
import RequireSession from "./RequireSession";
import { SessionProvider } from "./SessionProvider";

const ACCOUNT = { id: "synthetic", email: "reviewer@example.invalid", createdAt: "2026-09-04T00:00:00+00:00" };

/** A fetch where /api/auth/me answers as `signedIn` says, and refresh fails. */
function session(signedIn: boolean) {
  return vi.fn(async (url: string) => {
    if (url === "/api/auth/me" && signedIn) {
      return new Response(JSON.stringify({ user: ACCOUNT }), { status: 200 });
    }
    return new Response(JSON.stringify({ error: { message: "로그인이 필요합니다." } }), { status: 401 });
  });
}

function app(initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <SessionProvider>
        <Routes>
          <Route path="/login" element={<CredentialsPage mode="login" />} />
          <Route path="/signup" element={<CredentialsPage mode="signup" />} />
          <Route
            path="/app"
            element={
              <RequireSession>
                <p>다이어리 화면</p>
              </RequireSession>
            }
          />
          <Route path="/" element={<Navigate to="/app" replace />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  document.cookie = "__Host-pds_csrf=synthetic-csrf-value; path=/; secure";
});

afterEach(() => {
  document.cookie = "__Host-pds_csrf=; path=/; secure; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("without an account (T07-C03)", () => {
  beforeEach(() => vi.stubGlobal("fetch", session(false)));

  it("shows the login screen", async () => {
    app("/login");
    expect(await screen.findByRole("heading", { name: "로그인" })).toBeTruthy();
  });

  it("shows the signup screen", async () => {
    app("/signup");
    expect(await screen.findByRole("heading", { name: "가입하기" })).toBeTruthy();
  });

  it("sends a visitor to /app back to the login screen (T07-C97)", async () => {
    app("/app");
    expect(await screen.findByRole("heading", { name: "로그인" })).toBeTruthy();
    expect(screen.queryByText("다이어리 화면")).toBeNull();
  });

  it("sends / to the login screen too", async () => {
    app("/");
    expect(await screen.findByRole("heading", { name: "로그인" })).toBeTruthy();
  });

  it("does not decide before the session check has answered", async () => {
    // Rendering the redirect during the check would bounce every signed-in
    // reload through /login, which looks exactly like being logged out.
    app("/app");
    expect(screen.getByRole("status").textContent).toContain("확인하는 중");
  });
});

describe("with an account", () => {
  beforeEach(() => vi.stubGlobal("fetch", session(true)));

  it("lets the diary through", async () => {
    app("/app");
    expect(await screen.findByText("다이어리 화면")).toBeTruthy();
  });

  it("keeps a signed-in user off the login screen", async () => {
    app("/login");
    await waitFor(() => expect(screen.getByText("다이어리 화면")).toBeTruthy());
  });
});

describe("a session that ends while the app is open", () => {
  it("returns to the login screen when a request cannot be recovered", async () => {
    // The whole point of the session-lost event: a refresh that fails is not an
    // error message on a screen the user is no longer allowed to see.
    let signedIn = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/auth/me" && signedIn) {
          signedIn = false; // the session dies right after the first check
          return new Response(JSON.stringify({ user: ACCOUNT }), { status: 200 });
        }
        return new Response(JSON.stringify({ error: { message: "로그인이 필요합니다." } }), { status: 401 });
      }),
    );

    app("/app");
    expect(await screen.findByText("다이어리 화면")).toBeTruthy();

    const { sendWithSession } = await import("../api/http");
    // Inside act because the failed recovery reaches the provider through the
    // session-lost event, and that is a state update React wants to flush.
    await act(async () => {
      await sendWithSession("/api/plans");
    });

    await waitFor(() => expect(screen.queryByText("다이어리 화면")).toBeNull());
  });
});
