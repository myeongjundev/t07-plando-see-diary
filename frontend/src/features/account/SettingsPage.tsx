import AccountBar from "../../auth/AccountBar";
import { useSession } from "../../auth/SessionProvider";
import ThemeToggle from "../../ThemeToggle";
import ExportPanel from "../export/ExportPanel";
import AccountPanel from "./AccountPanel";

const joinedOn = (value?: string) => {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "long",
    timeZone: "Asia/Seoul",
  }).format(new Date(value));
};

export default function SettingsPage() {
  const { account } = useSession();

  return (
    <main className="settings-page">
      <div className="page-top">
        <header className="hero">
          <p className="eyebrow">ACCOUNT · SETTINGS</p>
          <h1>설정</h1>
          <p>프로필을 확인하고 로그인 보안과 내 데이터 보관을 관리합니다.</p>
        </header>
        <div className="page-top-actions">
          <AccountBar />
          <ThemeToggle />
        </div>
      </div>

      <nav className="settings-nav" aria-label="설정 구획 이동">
        <a href="#profile-settings"><span>01</span> 프로필</a>
        <a href="#data-settings"><span>02</span> 내 데이터</a>
        <a href="#security-settings"><span>03</span> 보안 및 계정</a>
      </nav>

      <section className="panel profile-panel" id="profile-settings" aria-label="프로필">
        <div className="section-heading">
          <div><span>01</span><h2>프로필</h2></div>
          <p>현재 로그인한 계정 정보입니다.</p>
        </div>
        <div className="profile-summary">
          <div className="profile-mark" aria-hidden="true">@</div>
          <dl>
            <div><dt>이메일</dt><dd>{account?.email}</dd></div>
            <div><dt>가입일</dt><dd>{joinedOn(account?.createdAt)}</dd></div>
          </dl>
        </div>
        <p className="profile-note">이메일은 로그인과 계정 식별에 사용됩니다. 비밀번호는 화면에 표시하지 않고, 세션 토큰은 localStorage에 보관하지 않습니다.</p>
      </section>

      <ExportPanel id="data-settings" />
      <AccountPanel id="security-settings" />
    </main>
  );
}
