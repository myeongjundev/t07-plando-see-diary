/** The login and signup screens. T07-C03, C94, C95.
 *
 * One component for both, because they are the same form and differ only in
 * which endpoint they post to and what the button says. Two files would drift.
 *
 * Open without a session on purpose: C03 asks that a reviewer with no account
 * can reach this far. Everything past it is gated.
 */
import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/http";
import { login, signup } from "../api/auth";
import { useSession } from "./SessionProvider";
import ThemeToggle from "../ThemeToggle";

// Matches MIN_PASSWORD_CHARS in app/services/accounts.py. Stated here so the
// user reads the rule before the server refuses them, not instead of it -- the
// server still checks, and this text is only ever advisory.
const MIN_PASSWORD_CHARS = 8;

interface Props {
  mode: "login" | "signup";
}

const COPY = {
  login: {
    heading: "로그인",
    lede: "계정으로 들어가면 본인이 쓴 계획만 보입니다.",
    submit: "로그인",
    working: "확인 중…",
    otherPrompt: "아직 계정이 없나요?",
    otherLabel: "가입하기",
    otherPath: "/signup",
  },
  signup: {
    heading: "가입하기",
    lede: "이메일과 비밀번호만 있으면 됩니다.",
    submit: "가입하고 시작하기",
    working: "만드는 중…",
    otherPrompt: "이미 계정이 있나요?",
    otherLabel: "로그인",
    otherPath: "/login",
  },
} as const;

export default function CredentialsPage({ mode }: Props) {
  const copy = COPY[mode];
  const { status, signedIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  // Someone who is already signed in has no business on this screen; sending
  // them on is friendlier than showing a form that would just replace their
  // session with the same one.
  if (status === "in") return <Navigate to="/app" replace />;

  const returnTo = (location.state as { from?: string } | null)?.from ?? "/app";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      // Signup does not open a session -- it creates an account and stops. The
      // login call right after is what signs the new user in, and it is the
      // same call the login screen makes, so there is one path into a session.
      if (mode === "signup") await signup({ email, password });
      signedIn(await login({ email, password }));
      navigate(returnTo, { replace: true });
    } catch (error) {
      setMessage(
        error instanceof ApiError || error instanceof Error
          ? error.message
          : "요청을 처리하지 못했습니다.",
      );
      // Never keep the typed password around after a failure. It is the one
      // value on this page worth clearing, and a retry should be deliberate.
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="page-top">
        <header className="hero">
          <p className="eyebrow">PLAN · DO · SEE</p>
          <h1>플랜두씨 다이어리</h1>
          <p>계획한 나와 실제의 차이를 기록하고, 다음 계획을 더 정확하게 만듭니다.</p>
        </header>
        <ThemeToggle />
      </div>

      <section className="panel auth-panel" aria-label={copy.heading}>
        <div className="section-heading">
          <div>
            <h2>{copy.heading}</h2>
          </div>
          <p>{copy.lede}</p>
        </div>
        <form onSubmit={submit}>
          <label>
            이메일
            <input
              type="email"
              name="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoFocus
            />
          </label>
          <label>
            비밀번호
            <input
              type="password"
              name="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              minLength={mode === "signup" ? MIN_PASSWORD_CHARS : undefined}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {mode === "signup" && (
            <p className="field-hint">비밀번호는 {MIN_PASSWORD_CHARS}자 이상이어야 합니다.</p>
          )}
          {message && (
            <p className="message" role="alert">
              {message}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? copy.working : copy.submit}
          </button>
        </form>
        <p className="auth-switch">
          {copy.otherPrompt} <Link to={copy.otherPath}>{copy.otherLabel}</Link>
        </p>
      </section>
    </main>
  );
}
