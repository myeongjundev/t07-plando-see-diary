/** The gate in front of /app. T07-C97.
 *
 * A visitor with no session is sent to /login and never sees the diary shell.
 * The redirect is a convenience, not the protection: every endpoint behind it
 * refuses the same visitor on its own. If this component were deleted the app
 * would show empty panels and a row of errors, not somebody else's diary.
 */
import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "./SessionProvider";

export default function RequireSession({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const location = useLocation();

  // Nothing is decided until /api/auth/me has answered. Rendering the redirect
  // during the check would bounce every signed-in reload through /login.
  if (status === "checking") {
    return (
      <main className="route-checking">
        <p role="status">로그인 상태를 확인하는 중입니다.</p>
      </main>
    );
  }

  if (status === "out") {
    // `replace` so Back goes where the user came from rather than back into a
    // redirect. The attempted path rides along so login can return them to it.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
