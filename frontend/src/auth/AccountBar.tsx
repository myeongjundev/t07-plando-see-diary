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
import { useNavigate } from "react-router-dom";
import { logout } from "../api/auth";
import { useSession } from "./SessionProvider";

export default function AccountBar() {
  const { account, signedOut } = useSession();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

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
    <div className="account-bar">
      <span className="account-email">{account?.email}</span>
      <button type="button" disabled={busy} onClick={() => void signOut()}>
        {busy ? "로그아웃 중…" : "로그아웃"}
      </button>
    </div>
  );
}
