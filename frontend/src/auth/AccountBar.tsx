/** Who is signed in, and the way out. T07-C109.
 *
 * Logout is a server call, not a cookie wipe: the session row is revoked first
 * and the browser's copy cleared second, so a lost response still leaves a dead
 * session rather than a live one the user believes is closed. The local state
 * is cleared whatever the call returns -- if the server could not be reached,
 * keeping the user in a screen they asked to leave helps nobody, and every
 * request from here on will 401 anyway.
 */
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { logout } from "../api/auth";
import { useSession } from "./SessionProvider";

export default function AccountBar() {
  const { account, signedOut } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const onSettings = location.pathname === "/settings";

  async function signOut() {
    setBusy(true);
    try {
      await logout();
    } catch {
      // Reported nowhere on purpose: see the note above.
    } finally {
      signedOut();
      navigate("/login", { replace: true });
    }
  }

  return (
    <nav className="account-bar" aria-label="계정 메뉴">
      <span className="account-email" title={account?.email}>{account?.email}</span>
      <Link className="account-action" to={onSettings ? "/app" : "/settings"}>
        {onSettings ? <DiaryIcon /> : <SettingsIcon />}
        <span>{onSettings ? "다이어리" : "설정"}</span>
      </Link>
      <button className="account-action" type="button" disabled={busy} onClick={() => void signOut()}>
        {busy ? "로그아웃 중…" : "로그아웃"}
      </button>
    </nav>
  );
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
    </svg>
  );
}

function DiaryIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M8 3v18M11 8h5M11 12h5" />
    </svg>
  );
}
