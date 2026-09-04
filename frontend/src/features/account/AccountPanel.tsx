/** 계정 화면 — 비밀번호 변경과 계정 삭제. T07-C114, C134.
 *
 * 설계 8절이 계정 화면 하나에 비밀번호 변경 · 내보내기 · 계정 삭제를 묶어 두었다.
 * 내보내기는 바로 위 구획(04)이 이미 하고 있어서 여기는 나머지 둘이다.
 *
 * 두 가지 모두 **비밀번호를 다시 받는다.** 세션만으로 되게 하면, 잠깐 자리를 비운
 * 화면이 「일기를 읽힐 기회」가 아니라 계정 탈취와 영구 삭제가 된다. 서버도 같은 것을
 * 요구하므로 여기서 안 받으면 그냥 400을 받는다 — 이 폼은 그 요구를 화면에 옮긴 것이지
 * 그 자체가 검사는 아니다.
 *
 * 삭제 폼이 아래에 있고, 확인 문구를 손으로 치게 한다. 되돌릴 수 없는 동작 하나가
 * 클릭 한 번 거리에 있으면 안 된다.
 */
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/http";
import { changePassword, deleteAccount } from "../../api/auth";
import { useSession } from "../../auth/SessionProvider";
import RevealButton from "../../auth/RevealButton";
import { assess } from "../../auth/passwordStrength";

/** 삭제를 확정하려면 이 글자를 그대로 쳐야 한다. */
const CONFIRM_PHRASE = "계정 삭제";

function messageOf(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : "요청을 처리하지 못했습니다.";
}

export default function AccountPanel() {
  const { account, signedOut } = useSession();
  const navigate = useNavigate();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [shownCurrent, setShownCurrent] = useState(false);
  const [shownNext, setShownNext] = useState(false);
  const [shownConfirmation, setShownConfirmation] = useState(false);
  const [changing, setChanging] = useState(false);
  const [changeMessage, setChangeMessage] = useState("");

  const [deletePassword, setDeletePassword] = useState("");
  const [shownDelete, setShownDelete] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState("");

  // 가입 화면과 같은 판정을 쓴다. 새 비밀번호가 다른 문으로 들어왔다고 다른 규칙을
  // 받으면 그건 두 번째 문이 아니라 우회로다.
  const grade = assess(next);
  const comparing = confirmation.length > 0;
  const mismatched = comparing && confirmation !== next;
  const canChange =
    current.length > 0 && grade.meetsPolicy && grade.level >= 2 && comparing && !mismatched;
  const canDelete = deletePassword.length > 0 && phrase.trim() === CONFIRM_PHRASE;

  async function submitChange(event: FormEvent) {
    event.preventDefault();
    setChanging(true);
    setChangeMessage("");
    try {
      await changePassword(current, next);
      // 응답이 새 쿠키를 싣고 온다. 이 세션은 이어지고 다른 기기는 전부 끊긴다.
      setChangeMessage("비밀번호를 바꿨습니다. 다른 기기의 로그인은 모두 해제되었습니다.");
    } catch (error) {
      setChangeMessage(messageOf(error));
    } finally {
      // 성공이든 실패든 세 칸을 비우고 다시 가린다. 화면에 남은 비밀번호는 주인이
      // 이미 안 보고 있는 화면에 떠 있는 비밀번호다.
      setCurrent("");
      setNext("");
      setConfirmation("");
      setShownCurrent(false);
      setShownNext(false);
      setShownConfirmation(false);
      setChanging(false);
    }
  }

  async function submitDelete(event: FormEvent) {
    event.preventDefault();
    setDeleting(true);
    setDeleteMessage("");
    try {
      await deleteAccount(deletePassword);
      // 서버가 쿠키를 지운 뒤다. 화면 상태를 비우고 로그인 화면으로 보낸다 — 남아
      // 있어 봐야 401만 받는 화면이다.
      signedOut();
      navigate("/login", { replace: true });
    } catch (error) {
      setDeleteMessage(messageOf(error));
      setDeletePassword("");
      setShownDelete(false);
      setDeleting(false);
    }
  }

  return (
    <section className="panel account-panel" aria-label="계정">
      <div className="section-heading">
        <div>
          <span>05</span>
          <h2>계정</h2>
        </div>
        <p>{account?.email}</p>
      </div>

      <form onSubmit={submitChange}>
        <h3>비밀번호 변경</h3>
        <label>
          현재 비밀번호
          <span className="password-field">
            <input
              type={shownCurrent ? "text" : "password"}
              name="currentPassword"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              required
            />
            <RevealButton
              shown={shownCurrent}
              onToggle={() => setShownCurrent((on) => !on)}
              label="현재 비밀번호"
            />
          </span>
        </label>
        <label>
          새 비밀번호
          <span className="password-field">
            <input
              type={shownNext ? "text" : "password"}
              name="newPassword"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
            <RevealButton
              shown={shownNext}
              onToggle={() => setShownNext((on) => !on)}
              label="새 비밀번호"
            />
          </span>
        </label>
        {next.length > 0 && (
          <div className="strength">
            <div className={`strength-bars level-${grade.level}`} aria-hidden="true">
              <span /> <span /> <span />
            </div>
            <p className="field-hint" aria-live="polite">
              비밀번호 강도: <strong>{grade.strength}</strong>
              {grade.advice && ` · ${grade.advice}`}
            </p>
          </div>
        )}
        <ul className="checklist">
          {grade.requirements.map((rule) => (
            <li key={rule.id} className={rule.met ? "met" : "unmet"}>
              <span aria-hidden="true">{rule.met ? "✓" : "○"}</span>
              {rule.label}
              {rule.recommended && <em>권장</em>}
              <span className="sr-only">{rule.met ? " 충족" : " 미충족"}</span>
            </li>
          ))}
        </ul>
        <label>
          새 비밀번호 확인
          <span className="password-field">
            <input
              type={shownConfirmation ? "text" : "password"}
              name="newPasswordConfirmation"
              autoComplete="new-password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              required
            />
            <RevealButton
              shown={shownConfirmation}
              onToggle={() => setShownConfirmation((on) => !on)}
              label="새 비밀번호 확인"
            />
          </span>
        </label>
        {comparing && (
          <p className={mismatched ? "field-hint unmet" : "field-hint met"} aria-live="polite">
            {mismatched ? "비밀번호가 일치하지 않습니다." : "✓ 비밀번호가 일치합니다."}
          </p>
        )}
        <p className="field-hint">
          비밀번호를 바꾸면 <strong>다른 기기의 로그인이 모두 해제됩니다.</strong> 이 기기는
          그대로 유지됩니다.
        </p>
        <button className="primary" disabled={changing || !canChange}>
          {changing ? "바꾸는 중…" : "비밀번호 바꾸기"}
        </button>
        {changeMessage && (
          <p className="message" role="status">
            {changeMessage}
          </p>
        )}
      </form>

      <form onSubmit={submitDelete} className="danger-zone">
        <h3>계정 삭제</h3>
        {/* C134가 요구하는 안내. 무엇이 지워지는지 목록으로 적는다 -- 「모든 자료」는
            읽는 사람이 무엇을 잃는지 세어 볼 수 없는 문장이다. */}
        <p className="field-hint unmet">
          계정을 삭제하면 <strong>계획 · 할 일 · 실행 기록 · 회고 · 규칙 변경 기록이 모두
          함께 지워지며, 되돌릴 수 없습니다.</strong> 남겨 두고 싶은 것이 있다면 먼저 위
          04 구획에서 내보내기를 하세요.
        </p>
        <label>
          비밀번호
          <span className="password-field">
            <input
              type={shownDelete ? "text" : "password"}
              name="deletePassword"
              autoComplete="current-password"
              value={deletePassword}
              onChange={(event) => setDeletePassword(event.target.value)}
              required
            />
            <RevealButton
              shown={shownDelete}
              onToggle={() => setShownDelete((on) => !on)}
              label="비밀번호"
            />
          </span>
        </label>
        <label>
          {/* 한 줄로 감싼다. `label`이 grid라서 감싸지 않으면 「확인을 위해」와
              「계정 삭제」와 「를 입력하세요」가 각각 한 줄씩 차지한다. */}
          <span>
            확인을 위해 <strong>「{CONFIRM_PHRASE}」</strong>를 입력하세요
          </span>
          <input
            type="text"
            name="confirmPhrase"
            value={phrase}
            onChange={(event) => setPhrase(event.target.value)}
            required
          />
        </label>
        <button className="danger" disabled={deleting || !canDelete}>
          {deleting ? "삭제하는 중…" : "계정과 모든 자료 삭제"}
        </button>
        {deleteMessage && (
          <p className="message" role="alert">
            {deleteMessage}
          </p>
        )}
      </form>
    </section>
  );
}
