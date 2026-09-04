/** 비밀번호 강도 — 약함 · 보통 · 강함, 그리고 실시간 체크리스트.
 *
 * 순수 함수로 떼어 둔 이유는 이것이 화면 로직이 아니라 **판정 규칙**이기 때문이다.
 * 화면은 결과를 그리기만 하고, 규칙은 `passwordStrength.test.ts`가 고정한다.
 *
 * ## 이 파일이 하는 판정과, 서버가 하는 판정
 *
 * 여기 판정은 **보조 기능이다.** 서버(`app/services/accounts.py`)가 같은 최소 정책 —
 * 8자 이상 · 영문 포함 · 숫자 포함 — 을 가입 경로에서 다시 본다. 프런트가 막았다는
 * 사실은 서버가 아무것도 확인하지 않아도 되는 근거가 아니다: 이 코드는 브라우저에서
 * 도는 코드고, 요청은 브라우저 없이도 보낼 수 있다.
 *
 * 대문자와 특수문자는 **권장이지 강제가 아니다.** 강제하면 사람은 `Password1!` 쪽으로
 * 몰리고, 그건 규칙을 만족하면서 추측하기 쉬운 비밀번호다. 그래서 최소 정책은 셋이고
 * 나머지는 등급을 올리는 요소로만 쓴다.
 *
 * ## 길이를 결정적으로 두는 이유
 *
 * 종류만 세면 등급이 거꾸로 나온다. `Abc!1234`는 네 종류를 다 갖춘 8자이고,
 * `말은 제주로 보내고 사람은 서울로`는 한 종류인 18자다. 추측에 드는 비용은 뒤쪽이
 * 압도적으로 크다. 그래서 짧으면 종류가 몇이든 「강함」이 되지 않는다.
 *
 * 한글·그 밖의 문자도 한 종류로 센다. ASCII 네 종류만 셌다면 이 앱을 쓰는 사람에게
 * 가장 좋은 비밀번호가 가장 나쁘게 표시된다.
 *
 * ## zxcvbn을 쓰지 않은 이유
 *
 * 검토했다. 추측 난이도를 사전과 자판 배열로 재는 쪽이 규칙 점수보다 정확한 것은
 * 맞지만, 사전을 포함하면 번들이 지금(약 292KB) 규모로 한 번 더 늘어난다. **보조
 * 표시 하나에 치를 값이 아니다** — 온라인 추측에 실제로 값을 물리는 것은 화면이 아니라
 * 서버의 로그인 잠금(설계 6절)이고, 그건 이미 있다.
 *
 * 대신 아래 `looksObvious`가 zxcvbn이 잡는 것 중 값싼 부분만 가져왔다: 같은 글자
 * 반복, 연속된 문자·숫자, 자판 한 줄, 흔한 단어. **남은 한계는 분명하다** — 유출 목록도
 * 개인 정보도 보지 않으므로 `Myeongjun2026!`은 여기서 「강함」이다. 설명서 ⑥에 적는다.
 */

export type Strength = "약함" | "보통" | "강함";

export interface Requirement {
  id: string;
  label: string;
  met: boolean;
  /** 최소 정책이 아니라 권장. 못 채워도 가입은 된다. */
  recommended: boolean;
}

export interface Assessment {
  strength: Strength;
  /** 1·2·3. 화면이 한국어 문자열로 분기하지 않게 하려고 같이 준다. */
  level: 1 | 2 | 3;
  requirements: Requirement[];
  /** 서버의 최소 정책을 만족하는가. 가입 버튼은 이것과 등급을 함께 본다. */
  meetsPolicy: boolean;
  /** 뻔한 패턴으로 걸렸는가. 걸리면 규칙을 다 채워도 「약함」이다. */
  obvious: boolean;
  /** 한 단계 올리려면 무엇이 필요한지. 「강함」이면 빈 문자열. */
  advice: string;
}

export const MIN_LENGTH = 8;
export const RECOMMENDED_LENGTH = 12;
/** 종류가 셋뿐이어도 이 길이를 넘으면 「강함」으로 본다. 문장 비밀번호의 자리. */
const PASSPHRASE_LENGTH = 16;

const LOWER = /[a-z]/;
const UPPER = /[A-Z]/;
const LETTER = /[A-Za-z]/;
const DIGIT = /[0-9]/;
// 허용 문자를 제한하지 않는다(지시 5절). 「특수문자」는 영문·숫자·공백이 아닌 모든
// 것이고, 한글도 여기 들어오지 않게 아래에서 따로 센다.
const SYMBOL = /[^a-zA-Z0-9\s\p{L}]/u;
/** 영문이 아닌 글자 — 한글 등. 종류를 셀 때만 쓴다. */
const OTHER_LETTER = /\p{L}/u;

/** 자판 한 줄과 흔한 조합. 길게 늘어놓기보다 실제로 자주 보이는 것만 둔다. */
const COMMON = [
  "password", "passwd", "qwerty", "asdfgh", "zxcvbn", "iloveyou", "admin",
  "letmein", "welcome", "dragon", "monkey", "sunshine", "princess", "football",
  "abc123", "1q2w3e", "qazwsx", "111111", "000000",
];

/** 연속으로 늘어선 것을 찾을 대상. 앞뒤 양방향 모두 본다. */
const RUNS = ["abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiop", "asdfghjkl", "zxcvbnm"];
const RUN_LENGTH = 5;

function classes(password: string): number {
  // 한글은 ASCII 영문을 지운 뒤에 본다. 그러지 않으면 `Diary한글`이 「영문」과
  // 「그 밖의 글자」를 한 번에 얻어 종류가 부풀려진다.
  const nonAscii = password.replace(/[a-zA-Z]/g, "");
  const found = [LOWER, UPPER, DIGIT, SYMBOL].filter((pattern) => pattern.test(password));
  return found.length + (OTHER_LETTER.test(nonAscii) ? 1 : 0);
}

/**
 * 규칙을 다 채우고도 몇 초면 뚫리는 것들. 이게 없으면 `qwerty123`이 「보통」이 된다.
 *
 * 부분 문자열로 본다. `Qwerty123!`처럼 앞뒤에 조금 붙인 것은 붙이기 전과 거의 같은
 * 값이고, 공격자의 사전은 그 변형을 이미 알고 있다.
 */
export function looksObvious(password: string): boolean {
  const text = password.toLowerCase();
  if (!text) return false;
  // 같은 글자만으로 된 것, 또는 같은 글자가 네 번 이상 이어지는 것.
  if (/^(.)\1*$/u.test(text) || /(.)\1{3,}/u.test(text)) return true;

  for (const row of RUNS) {
    const reversed = [...row].reverse().join("");
    for (const source of [row, reversed]) {
      for (let start = 0; start + RUN_LENGTH <= source.length; start += 1) {
        if (text.includes(source.slice(start, start + RUN_LENGTH))) return true;
      }
    }
  }

  for (const word of COMMON) {
    // 짧은 비밀번호는 단어가 들어 있다는 것만으로 걸리고, 긴 것은 단어가 절반
    // 이상을 차지할 때만 걸린다. 긴 문장 안에 흔한 단어 하나가 섞인 것까지
    // 「약함」이라고 하면 안내가 아니라 방해가 된다.
    if (!text.includes(word)) continue;
    if (text.length < RECOMMENDED_LENGTH || word.length * 2 >= text.length) return true;
  }
  return false;
}

export function assess(password: string): Assessment {
  // 공백은 길이로 센다. 문장 비밀번호에서 단어 사이를 벌리는 실제 문자이고, 빼고
  // 세면 가장 긴 것을 가장 짧게 평가하게 된다.
  const length = [...password].length;
  const hasLetter = LETTER.test(password);
  const hasDigit = DIGIT.test(password);
  const hasSymbol = SYMBOL.test(password);

  const requirements: Requirement[] = [
    { id: "length", label: `${MIN_LENGTH}자 이상`, met: length >= MIN_LENGTH, recommended: false },
    { id: "letter", label: "영문 포함", met: hasLetter, recommended: false },
    { id: "digit", label: "숫자 포함", met: hasDigit, recommended: false },
    { id: "symbol", label: "특수문자 포함", met: hasSymbol, recommended: true },
    // 「권장」은 목록의 배지가 말한다. 이름에까지 넣으면 「12자 이상 권장 (권장)」이 된다.
    { id: "long", label: `${RECOMMENDED_LENGTH}자 이상`, met: length >= RECOMMENDED_LENGTH, recommended: true },
  ];

  const meetsPolicy = requirements.every((rule) => rule.recommended || rule.met);
  const obvious = looksObvious(password);
  const variety = classes(password);

  const strong =
    (length >= RECOMMENDED_LENGTH && LOWER.test(password) && UPPER.test(password) && hasDigit && hasSymbol) ||
    (length >= PASSPHRASE_LENGTH && variety >= 3);

  const strength: Strength = !meetsPolicy || obvious ? "약함" : strong ? "강함" : "보통";

  return {
    strength,
    level: strength === "약함" ? 1 : strength === "보통" ? 2 : 3,
    requirements,
    meetsPolicy,
    obvious,
    advice: adviceFor(strength, { length, obvious, meetsPolicy, hasSymbol }),
  };
}

interface Facts {
  length: number;
  obvious: boolean;
  meetsPolicy: boolean;
  hasSymbol: boolean;
}

function adviceFor(strength: Strength, { length, obvious, meetsPolicy, hasSymbol }: Facts): string {
  if (strength === "강함") return "";
  // 뻔한 패턴이 먼저다. 여기 걸린 사람에게 「12자를 넘기세요」라고 하면
  // `password1234`가 나온다.
  if (obvious) return "연속된 문자나 흔한 단어는 피해 주세요.";
  if (!meetsPolicy) return `${MIN_LENGTH}자 이상, 영문과 숫자를 함께 넣어 주세요.`;
  // 길이를 먼저 권한다. 같은 노력이면 길이가 값을 더 크게 올리고, 무엇보다 사람이
  // 기억할 수 있는 쪽이 길이다.
  if (length < RECOMMENDED_LENGTH) return `${RECOMMENDED_LENGTH}자를 넘기면 강해집니다.`;
  if (!hasSymbol) return "특수문자나 대문자를 섞으면 강해집니다.";
  return `${PASSPHRASE_LENGTH}자를 넘기면 강해집니다.`;
}
