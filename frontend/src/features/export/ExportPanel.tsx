import { useState } from "react";
import { sendWithSession } from "../../api/http";

export default function ExportPanel() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function download() {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      // Through the session client: an export started ten minutes into a session
      // must refresh rather than download an error page.
      const response = await sendWithSession("/api/export");
      if (!response.ok) throw new Error("내보내지 못했습니다. 잠시 후 다시 시도하세요.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = "t06-diary-v2.json";
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage("전체 자료의 JSON 파일 다운로드를 시작했습니다.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "파일을 내려받지 못했습니다."); }
    finally { setBusy(false); }
  }
  return <section className="panel export-panel">
    <div className="section-heading"><div><span>04</span><h2>내 자료 내보내기</h2></div><p>계획부터 회고까지 한 파일에 보관합니다.</p></div>
    <p>서버에 저장된 모든 계획·수정 이력·할 일·태그·완료 이력·실행 기록·회고를 포함합니다. 삭제한 할 일의 보관 기록도 함께 내보냅니다.</p>
    <button className="primary" disabled={busy} onClick={() => void download()}>{busy ? "내보내는 중…" : "전체 JSON 내려받기"}</button>
    {message && <p role="status" className="message">{message}</p>}
  </section>;
}
