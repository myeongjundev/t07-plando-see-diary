/** 비밀번호 칸의 눈 아이콘. 가입 화면과 계정 화면이 함께 쓴다.
 *
 * `type="button"`이 이 파일에서 가장 중요한 한 줄이다. 폼 안의 `<button>`은 기본이
 * submit이라, 이게 없으면 「내가 뭘 쳤나」 보려던 클릭이 제출이 된다. 계정 화면에서
 * 그 제출은 **계정 삭제**다.
 */
export default function RevealButton({
  shown,
  onToggle,
  label,
}: {
  shown: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className="reveal"
      onClick={onToggle}
      aria-pressed={shown}
      aria-label={shown ? `${label} 가리기` : `${label} 보기`}
    >
      {/* 아이콘은 장식이라 aria-hidden. 무엇을 하는 단추인지는 aria-label이 말한다. */}
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
        <path
          d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="12" cy="12" r="2.8" fill="none" stroke="currentColor" strokeWidth="1.8" />
        {shown && (
          <path d="M4 20 20 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        )}
      </svg>
    </button>
  );
}
