/** What the frontend knows about being signed in. Design section 8.
 *
 * It knows one thing: whether `GET /api/auth/me` answered. No token, no expiry,
 * nothing in localStorage -- the browser holds the session in cookies this code
 * cannot read, and the server is the only thing that can say what they are
 * worth. That is what makes the route gate below un-talk-out-of-able: editing
 * client state cannot manufacture a session, it can only manufacture a redirect
 * to a screen that will 401 anyway.
 */
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Account, currentAccount } from "../api/auth";
import { onSessionLost } from "../api/http";

type Status = "checking" | "in" | "out";

interface Session {
  status: Status;
  account: Account | null;
  /** Record a sign-in the caller has already completed. */
  signedIn: (account: Account) => void;
  /** Record a sign-out, whether the user asked for it or the server imposed it. */
  signedOut: () => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [status, setStatus] = useState<Status>("checking");

  const signedIn = useCallback((next: Account) => {
    setAccount(next);
    setStatus("in");
  }, []);

  const signedOut = useCallback(() => {
    setAccount(null);
    setStatus("out");
  }, []);

  useEffect(() => {
    let cancelled = false;
    currentAccount()
      .then((found) => {
        if (cancelled) return;
        if (found) signedIn(found);
        else signedOut();
      })
      .catch(() => {
        // The check itself failed -- offline, or the server is down. Treated as
        // signed out so the app does not sit on "checking" forever; the login
        // screen will report the real error when the user tries.
        if (!cancelled) signedOut();
      });
    return () => {
      cancelled = true;
    };
  }, [signedIn, signedOut]);

  // A request that could not be recovered by a refresh means the session is
  // gone -- idle timeout, absolute expiry, or a logout in another tab. Same
  // effect either way.
  useEffect(() => onSessionLost(signedOut), [signedOut]);

  const value = useMemo<Session>(
    () => ({ status, account, signedIn, signedOut }),
    [status, account, signedIn, signedOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("SessionProvider 안에서만 쓸 수 있습니다.");
  return session;
}
