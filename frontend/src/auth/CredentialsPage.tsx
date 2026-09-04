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
import { MIN_LENGTH, assess } from "./passwordStrength";
import RevealButton from "./RevealButton";
import ThemeToggle from "../ThemeToggle";

// Mirrors EMAIL_PATTERN in app/services/accounts.py, and is deliberately just
// as permissive. A stricter one here would disable the button for an address
// the server would have accepted, which is a rejection with no appeal.
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

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
  // One toggle per field, as asked. They are independent because the reason to
  // reveal one is usually to compare it against the other still hidden.
  const [revealed, setRevealed] = useState(false);
  const [revealedConfirmation, setRevealedConfirmation] = useState(false);
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
  const matched = confirming && !mismatched;

  // Assessed from the first character, not from the floor: the use of a meter
  // is that it moves while a password is being chosen, and one that appears
  // only after the field is already valid arrives too late to change anything.
  const grade = assess(password);
  const signupReady =
    EMAIL_PATTERN.test(email.trim()) && grade.meetsPolicy && grade.level >= 2 && matched;
  // On the login screen none of this applies. Gating that button on today's
  // policy would lock out an account created under yesterday's -- the one the
  // T06 data was claimed into among them.
  const ready = mode === "signup" ? signupReady : email.length > 0 && password.length > 0;

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
      setRevealedConfirmation(false);
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
                minLength={mode === "signup" ? MIN_LENGTH : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              <RevealButton
                shown={revealed}
                onToggle={() => setRevealed((on) => !on)}
                label="비밀번호"
              />
            </span>
          </label>

          {mode === "signup" && password.length > 0 && (
            <div className="strength">
              {/* aria-hidden: 세 칸은 바로 옆 글자를 그림으로 옮긴 것뿐이라, 화면
                  낭독기에 「채워짐 채워짐 빔」이 들릴 이유가 없다. 등급은 글자로
                  읽힌다 — 색만으로 상태를 전하지 않는다. */}
              <div className={`strength-bars level-${grade.level}`} aria-hidden="true">
                <span /> <span /> <span />
              </div>
              {/* aria-live, because this changes under a field being typed in.
                  Announced only on focus, it would still be reading the grade
                  from four characters ago. */}
              <p className="field-hint" aria-live="polite">
                비밀번호 강도: <strong>{grade.strength}</strong>
                {grade.advice && ` · ${grade.advice}`}
              </p>
            </div>
          )}

          {mode === "signup" && (
            <ul className="checklist">
              {grade.requirements.map((rule) => (
                <li key={rule.id} className={rule.met ? "met" : "unmet"}>
                  <span aria-hidden="true">{rule.met ? "✓" : "○"}</span>
                  {rule.label}
                  {/* 권장 항목은 못 채워도 가입된다. 그 사실이 목록에 적혀 있지
                      않으면 다섯 줄이 전부 요구사항으로 읽힌다. */}
                  {rule.recommended && <em>권장</em>}
                  <span className="sr-only">{rule.met ? " 충족" : " 미충족"}</span>
                </li>
              ))}
            </ul>
          )}

          {mode === "signup" && (
            <label>
              비밀번호 확인
              <span className="password-field">
                <input
                  type={revealedConfirmation ? "text" : "password"}
                  name="passwordConfirmation"
                  autoComplete="new-password"
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  required
                />
                <RevealButton
                  shown={revealedConfirmation}
                  onToggle={() => setRevealedConfirmation((on) => !on)}
                  label="비밀번호 확인"
                />
              </span>
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
          <button className="primary" disabled={busy || !ready}>
            {busy ? copy.working : copy.submit}
          </button>
          {mode === "signup" && !ready && !busy && (
            // A disabled button with no explanation is a dead end. The list and
            // the meter above say what is missing; this says that they are the
            // reason the button will not move.
            <p className="field-hint" aria-live="polite">
              위 조건을 모두 채우면 가입할 수 있습니다.
            </p>
          )}
        </form>
        <p className="auth-switch">
          {copy.otherPrompt} <Link to={copy.otherPath}>{copy.otherLabel}</Link>
        </p>
      </section>
    </main>
  );
}
