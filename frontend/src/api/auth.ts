import { request, sendWithSession } from "./http";

export interface Account {
  id: string;
  email: string;
  createdAt: string;
}

export interface Credentials {
  email: string;
  password: string;
}

export function signup(credentials: Credentials) {
  return request<{ user: Account }>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(credentials),
  }).then((body) => body.user);
}

export function login(credentials: Credentials) {
  return request<{ user: Account }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  }).then((body) => body.user);
}

export function logout() {
  return request<{ ok: true }>("/api/auth/logout", { method: "POST", body: "{}" });
}

/** Who the browser is, according to cookies it cannot read.
 *
 * The only way the frontend learns it is signed in. Returns null on 401 rather
 * than throwing, because "not signed in" is an answer, not a failure.
 *
 * Goes through the session client, so someone returning to an open tab after
 * more than ten minutes is refreshed back in rather than shown the login
 * screen. The cost is that a genuinely signed-out visitor spends one refresh
 * attempt finding that out, which is the right way round: the common case is
 * a real session, and getting it wrong logs a real user out.
 */
export async function currentAccount(): Promise<Account | null> {
  const response = await sendWithSession("/api/auth/me");
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("로그인 상태를 확인하지 못했습니다.");
  return ((await response.json()) as { user: Account }).user;
}
