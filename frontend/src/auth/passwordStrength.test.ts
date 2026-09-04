/** 강도 판정 규칙. 화면이 아니라 규칙을 고정한다.
 *
 * 지시 2·3절의 예시가 그대로 검사로 들어와 있다. 여기 검사 중 상당수는 「이 등급이
 * 나온다」가 아니라 **「이 등급은 나오지 않는다」** 다. 강도 표시가 실제로 해로워지는
 * 방식은 짧고 뻔한 비밀번호를 칭찬하는 것이고, 그건 종류만 세는 판정이 늘 하는 일이다.
 */
import { describe, expect, it } from "vitest";
import { assess, looksObvious } from "./passwordStrength";

const grade = (password: string) => assess(password).strength;
const met = (password: string, id: string) =>
  assess(password).requirements.find((rule) => rule.id === id)!.met;

describe("약함 — 지시 2절의 목록", () => {
  it.each([
    ["8자 미만", "Ab1!"],
    ["숫자만", "12345678"],
    ["영문만", "passwordonly"],
    ["연속된 숫자", "12345678"],
    ["흔한 단어", "password"],
    ["자판 한 줄 + 숫자", "qwerty123"],
    ["동일 문자 반복", "aaaaaaaaaaaa"],
  ])("%s → 약함", (_label, password) => {
    expect(grade(password)).toBe("약함");
  });

  it("규칙을 다 채워도 뻔한 패턴이면 약함", () => {
    // `Password1!` 은 어떤 구성 규칙도 만족하고 모든 추측 목록에 들어 있다. 규칙
    // 점수만 세는 판정이 「강함」이라고 말하는 자리다.
    expect(assess("Password1!").meetsPolicy).toBe(true);
    expect(grade("Password1!")).toBe("약함");
  });
});

describe("보통 — 지시 2절의 예시", () => {
  it.each(["Hello2026", "diary1234!"])("%s → 보통", (password) => {
    expect(grade(password)).toBe("보통");
  });

  it("영문과 숫자만으로도 보통에 닿는다", () => {
    // 특수문자와 대문자는 권장이지 강제가 아니다. 강제하면 사람은 `Password1!`
    // 쪽으로 몰린다.
    expect(grade("diarydiary9")).toBe("보통");
  });
});

describe("강함 — 지시 3절의 예시", () => {
  it.each(["Diary!Cloud2026", "MySecure#Diary27"])("%s → 강함", (password) => {
    expect(grade(password)).toBe("강함");
  });

  it("네 종류를 갖춘 여덟 자는 강함이 아니다", () => {
    // 지시 3절이 이름을 대어 막은 경우. 길이가 결정적이라는 것이 여기서 드러난다.
    expect(grade("Abc!1234")).not.toBe("강함");
  });

  it("긴 한글 문장은 종류가 하나여도 강함", () => {
    // ASCII 네 종류만 셌다면 이 앱을 쓰는 사람에게 가장 좋은 비밀번호가 가장 나쁘게
    // 표시된다. 다만 최소 정책상 영문과 숫자가 있어야 가입되므로 둘을 섞어 본다.
    expect(grade("계획 대 실제 diary 2026")).toBe("강함");
  });
});

describe("체크리스트", () => {
  it("다섯 줄이 실시간으로 바뀐다", () => {
    expect(assess("").requirements.map((rule) => rule.id)).toEqual([
      "length", "letter", "digit", "symbol", "long",
    ]);
    expect(met("abcdefgh", "length")).toBe(true);
    expect(met("abcdefg", "length")).toBe(false);
    expect(met("12345678", "letter")).toBe(false);
    expect(met("abcdefgh", "digit")).toBe(false);
    expect(met("abcdefg1!", "symbol")).toBe(true);
    expect(met("abcdefg1", "symbol")).toBe(false);
    expect(met("abcdefghijk1", "long")).toBe(true);
  });

  it("권장 항목은 권장으로 표시된다", () => {
    const recommended = assess("").requirements.filter((rule) => rule.recommended);
    expect(recommended.map((rule) => rule.id)).toEqual(["symbol", "long"]);
  });

  it("최소 정책은 길이·영문·숫자 셋뿐이다", () => {
    // 서버(`accounts.py`)가 보는 것과 같은 셋. 하나라도 더 넣으면 화면이 서버보다
    // 엄격해지고, 서버가 받아 줄 비밀번호를 화면이 막게 된다.
    expect(assess("diarydiary9").meetsPolicy).toBe(true);
    expect(assess("diarydiaryd").meetsPolicy).toBe(false);
    expect(assess("1234567890").meetsPolicy).toBe(false);
    expect(assess("diary9").meetsPolicy).toBe(false);
  });
});

describe("뻔한 패턴 탐지", () => {
  it("연속된 문자·숫자와 자판 한 줄을 잡는다", () => {
    expect(looksObvious("abcde")).toBe(true);
    expect(looksObvious("54321")).toBe(true);
    expect(looksObvious("asdfg")).toBe(true);
  });

  it("네 자리 연속은 잡지 않는다", () => {
    // `diary1234!` 를 「보통」으로 두기 위한 경계. 지시 2절이 그 예를 보통으로 적었다.
    expect(looksObvious("1234")).toBe(false);
  });

  it("긴 문장 안에 섞인 흔한 단어 하나까지 잡지는 않는다", () => {
    // 안내가 방해가 되는 지점. 단어가 절반 이상을 차지할 때만 걸린다.
    expect(looksObvious("admin")).toBe(true);
    expect(looksObvious("계획 대 실제 admin diary 2026")).toBe(false);
  });
});

describe("안내 문구", () => {
  it("뻔한 패턴이 먼저다", () => {
    // 여기 걸린 사람에게 「12자를 넘기세요」라고 하면 `password1234`가 나온다.
    expect(assess("qwerty123").advice).toContain("흔한 단어");
  });

  it("최소 정책을 못 채우면 그것부터 말한다", () => {
    expect(assess("diarydiaryd").advice).toContain("영문과 숫자");
  });

  it("길이를 종류보다 먼저 권한다", () => {
    expect(assess("Hello2026").advice).toContain("12자");
  });

  it("강함이면 더 권하지 않는다", () => {
    expect(assess("Diary!Cloud2026").advice).toBe("");
  });
});

describe("판정은 예외를 던지지 않는다", () => {
  it("빈 문자열에도 답한다", () => {
    // 화면은 첫 글자부터 이 함수를 부른다. 여기서 던지면 가입 화면이 빈 화면이 된다.
    expect(grade("")).toBe("약함");
    expect(assess("").meetsPolicy).toBe(false);
  });
});
