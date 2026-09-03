/** The one place a request leaves this app. Design section 8.
 *
 * Every API call in the frontend goes through `sendWithSession`, which does two
 * things no individual caller should have to remember:
 *
 *  1. Copies the readable CSRF cookie into `X-CSRF-Token` on state-changing
 *     requests, because the server refuses them without it (design section 5).
 *  2. Recovers from a 401 caused by the access token reaching ten minutes,
 *     which is a thing the user must never be made to notice.
 *
 * No token value is read, stored, or logged here. The access and refresh
 * cookies are HttpOnly and this file could not read them if it tried; the CSRF
 * cookie is readable on purpose and is not a credential.
 */

const CSRF_COOKIE = "__Host-pds_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const REFRESH_URL = "/api/auth/refresh";

// Methods the server treats as state-changing. GET and HEAD are excluded here
// for the same reason the server excludes them: they carry no CSRF requirement,
// and sending a header the server does not look at only invites a caller to
// believe it matters.
const READ_ONLY = new Set(["GET", "HEAD"]);

interface ApiErrorBody {
  error?: { message?: string; details?: Record<string, string> };
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly details: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Read the double-submit value the server set at login.
 *
 * Absent before the first login and after logout, which is correct: those are
 * the requests that do not carry one.
 */
export function csrfToken(): string | null {
  for (const pair of document.cookie.split("; ")) {
    const separator = pair.indexOf("=");
    if (separator > 0 && pair.slice(0, separator) === CSRF_COOKIE) {
      return decodeURIComponent(pair.slice(separator + 1));
    }
  }
  return null;
}

function withSessionHeaders(init?: RequestInit): RequestInit {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (!READ_ONLY.has(method)) {
    const token = csrfToken();
    if (token) headers[CSRF_HEADER] = token;
  }
  // Explicit rather than relying on the default. The default is same-origin
  // today, and a cookie-carried session is not a thing to leave to a default.
  return { credentials: "same-origin", ...init, headers };
}

// ---------------------------------------------------------------------------
// Serialising the refresh
//
// Five components can hit 401 in the same tick -- the plan list, the summary,
// three panels -- and five refreshes would rotate the refresh token five times.
// Four of those rotations spend a token another one already replaced, which is
// indistinguishable from a stolen token being replayed and, once step 14 lands,
// revokes the whole family. The user gets logged out for using the app.
//
// So refreshes are serialised, and the body of the critical section re-sends
// the original request first. Whoever gets in second finds their request now
// succeeds with the cookie the first one obtained, and never refreshes at all.
// That single mechanism covers both cases: within a tab the queue orders them,
// across tabs the Web Lock does, and the re-check is what turns "wait" into
// "no second refresh".
// ---------------------------------------------------------------------------

const LOCK_NAME = "pds-session-refresh";

let queue: Promise<unknown> = Promise.resolve();

/** Run `work` after every earlier call to this function has finished. */
function serialize<T>(work: () => Promise<T>): Promise<T> {
  // Both arms are `work`: a rejected predecessor must not cancel the queue.
  const run = queue.then(work, work);
  queue = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}

const channel: BroadcastChannel | null =
  typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("pds-session");

// Fallback state for browsers without Web Locks. `peerBusyUntil` expires on its
// own so that a tab closed mid-refresh cannot wedge the others.
const PEER_TIMEOUT_MS = 5000;
let peerBusyUntil = 0;
let peerFinished: (() => void) | null = null;

channel?.addEventListener("message", (event: MessageEvent) => {
  if (event.data === "refresh:start") peerBusyUntil = Date.now() + PEER_TIMEOUT_MS;
  if (event.data === "refresh:end") {
    peerBusyUntil = 0;
    peerFinished?.();
  }
});

function waitForPeer(): Promise<void> {
  const remaining = peerBusyUntil - Date.now();
  if (remaining <= 0) return Promise.resolve();
  return new Promise<void>((resolve) => {
    const timer = setTimeout(finish, remaining);
    peerFinished = finish;
    function finish() {
      clearTimeout(timer);
      peerFinished = null;
      resolve();
    }
  });
}

function locks(): LockManager | undefined {
  return typeof navigator === "undefined" ? undefined : navigator.locks;
}

/** Hold the refresh slot for this origin while `work` runs. */
function exclusive<T>(work: () => Promise<T>): Promise<T> {
  const manager = locks();
  if (manager) return serialize(() => manager.request(LOCK_NAME, work) as Promise<T>);
  // No Web Locks: wait out any peer that announced a refresh, then announce our
  // own. Weaker than a lock -- two tabs can still start together -- but it
  // turns the common case (one tab wakes, the other is idle) into the same
  // shape, and the re-check inside `work` does the rest.
  return serialize(async () => {
    await waitForPeer();
    channel?.postMessage("refresh:start");
    try {
      return await work();
    } finally {
      channel?.postMessage("refresh:end");
    }
  });
}

const sessionLost = new EventTarget();

/** Fires when a request could not be recovered by a refresh.
 *
 * The route gate listens, so an expired session becomes a redirect to /login
 * rather than an error message on a screen the user is no longer allowed to
 * see. Carries nothing: there is nothing about a dead session worth passing on.
 */
export function onSessionLost(listener: () => void): () => void {
  sessionLost.addEventListener("session-lost", listener);
  return () => sessionLost.removeEventListener("session-lost", listener);
}

async function rotate(): Promise<boolean> {
  const response = await fetch(REFRESH_URL, {
    method: "POST",
    credentials: "same-origin",
    headers: withSessionHeaders({ method: "POST" }).headers as Record<string, string>,
    // A body, because the server requires application/json on every
    // state-changing request and a Content-Type with no body is a lie.
    body: "{}",
  });
  return response.ok;
}

/** Fetch with the session attached, refreshing once if the access token aged out. */
export async function sendWithSession(url: string, init?: RequestInit): Promise<Response> {
  const attempt = () => fetch(url, withSessionHeaders(init));
  const first = await attempt();
  // Refresh's own 401 means the refresh cookie is gone or spent. Retrying it
  // would recurse, and there is nothing left to recover with.
  if (first.status !== 401 || url === REFRESH_URL) return first;

  const recovered = await exclusive(async () => {
    // Someone may have refreshed while we waited. Ask again before spending a
    // rotation of our own.
    const again = await attempt();
    if (again.status !== 401) return again;
    if (!(await rotate())) return again;
    return attempt();
  });

  if (recovered.status === 401) sessionLost.dispatchEvent(new Event("session-lost"));
  return recovered;
}

/** The JSON-shaped call the api modules use. */
export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await sendWithSession(url, init);
  if (response.status === 204) return undefined as T;
  const body = (await response.json().catch(() => ({}))) as T & ApiErrorBody;
  if (!response.ok) {
    const details = body.error?.details ?? {};
    const detail = Object.values(details)[0];
    throw new ApiError(
      detail ?? body.error?.message ?? "요청을 처리하지 못했습니다.",
      response.status,
      details,
    );
  }
  return body;
}

/** Reset the module's serialisation state. Tests only. */
export function resetSessionPlumbing(): void {
  queue = Promise.resolve();
  peerBusyUntil = 0;
  peerFinished = null;
}
