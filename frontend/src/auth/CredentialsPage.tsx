/** The login and signup screens. T07-C03, C94, C95.
 *
 * One component for both, because they are the same form and differ only in
 * which endpoint they post to and what the button says. Two files would drift.
 *
 * Open without a session on purpose: C03 asks that a reviewer with no account
 * can reach this far. Everything past it is gated.
 *
 * What this screen deliberately does not have, because both would undo work
 * done elsewhere rather than merely being unbuilt:
 *
 * - **A live "is this address taken" check.** Signup's 409 already tells a
 *   caller that one address exists, which C98 requires and design section 11
 *   records as a limitation. An endpoint answering that on every keystroke
 *   turns a single admission into bulk enumeration, and wastes everything the
 *   login path spends to hide the same fact -- the dummy Argon2 verification,
 *   the identical wording and status (C99), and a throttle that refuses a
 *   locked caller whether or not the account is real.
 * - **Composition rules (letters, digits, symbols).** Absent for the reason
 *   written at MIN_PASSWORD_CHARS in app/services/accounts.py: they push people
 *   toward predictable substitutions and shorter passwords. The floor is a
 *   length, and what costs an online guesser is the throttle.
 *
 * Everything below is advisory. The server validates the same things again, and
 * none of these checks is what decides whether an account is created.
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
  const [confirmation, setConfirmation] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  // Someone who is already signed in has no business on this screen; sending
  // them on is friendlier than showing a form that would just replace their
  // session with the same one.
  if (status === "in") return <Navigate to="/app" replace />;

  const returnTo = (location.state as { from?: string } | null)?.from ?? "/app";

  // Signup only, and only once the second field has something in it: telling
  // someone their passwords do not match before they have typed the first
  // character of the second one is noise, not help.
  const confirming = mode === "signup" && confirmation.length > 0;
  const mismatched = confirming && confirmation !== password;
  const longEnough = password.length >= MIN_PASSWORD_CHARS;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mismatched) {
      // Caught here so a typo in the confirmation cannot become an account with
      // a password its owner cannot reproduce. The server never sees this field
      // -- there is nothing for it to check -- which is also why this is not a
      // security check and nothing downstream may rely on it.
      setMessage("비밀번호가 일치하지 않습니다.");
      return;
    }
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
      // Re-hiding goes with that: a revealed field left on screen after a
      // failed attempt is a password in plain sight on a screen whose owner has
      // stopped looking at it.
      setPassword("");
      setConfirmation("");
      setRevealed(false);
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
            <span className="password-field">
              <input
                type={revealed ? "text" : "password"}
                name="password"
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                minLength={mode === "signup" ? MIN_PASSWORD_CHARS : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              {/* type=button, or it submits. A button in a form defaults to
                  submit, and the bug that makes is a signup attempt fired by
                  someone who only wanted to look at what they had typed. */}
              <button
                type="button"
                className="reveal"
                onClick={() => setRevealed((shown) => !shown)}
                aria-pressed={revealed}
                aria-label={revealed ? "비밀번호 가리기" : "비밀번호 보기"}
              >
                {revealed ? "가리기" : "보기"}
              </button>
            </span>
          </label>
          {mode === "signup" && (
            // aria-live, because the text changes under a field being typed in:
            // announced only on focus, it would still be saying "8자 이상이어야
            // 합니다" long after that stopped being true.
            <p className={longEnough ? "field-hint met" : "field-hint"} aria-live="polite">
              {longEnough
                ? `✓ ${MIN_PASSWORD_CHARS}자 이상`
                : `비밀번호는 ${MIN_PASSWORD_CHARS}자 이상이어야 합니다.`}
            </p>
          )}
          {mode === "signup" && (
            <label>
              비밀번호 확인
              <input
                type={revealed ? "text" : "password"}
                name="passwordConfirmation"
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                required
              />
            </label>
          )}
          {confirming && (
            <p className={mismatched ? "field-hint unmet" : "field-hint met"} aria-live="polite">
              {mismatched ? "비밀번호가 일치하지 않습니다." : "✓ 비밀번호가 일치합니다."}
            </p>
          )}
          {message && (
            <p className="message" role="alert">
              {message}
            </p>
          )}
          <button className="primary" disabled={busy || mismatched}>
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
