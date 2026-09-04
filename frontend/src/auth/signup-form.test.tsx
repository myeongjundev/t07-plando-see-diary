/** 가입 화면의 실시간 안내 — 체크리스트 · 강도 · 확인 · 보기/숨김 · 버튼 활성화.
 *
 * 판정 규칙 자체는 `passwordStrength.test.ts`가 고정한다. 여기서 보는 것은 그 결과가
 * 화면에 어떻게 이어지는지다: 입력 → 조건 충족 → 강도 → 일치 → 가입 가능.
 *
 * 이 중 무엇도 보안 경계가 아니다. 서버가 최소 정책을 다시 보고(`accounts.py`), 확인
 * 칸은 서버로 가지도 않는다. 여기서 검사할 값어치가 있는 것은 안내가 **방해가 되지
 * 않는지** 다 — 눈 아이콘이 폼을 제출하지 않는지, 실패한 시도가 화면에 아무것도 남기지
 * 않는지.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CredentialsPage from "./CredentialsPage";
import { SessionProvider } from "./SessionProvider";

const EMAIL = "synthetic@example.invalid";
/** 최소 정책을 만족하고 「보통」인 합성 값. 가입 버튼이 열리는 최소 조건이다. */
const PASSWORD = "합성-비밀번호-4b2e";

function signedOut() {
  return vi.fn(async () =>
    new Response(JSON.stringify({ error: { message: "로그인이 필요합니다." } }), { status: 401 }),
  );
}

function screenFor(mode: "login" | "signup") {
  return render(
    <MemoryRouter initialEntries={[`/${mode}`]}>
      <SessionProvider>
        <Routes>
          <Route path="/login" element={<CredentialsPage mode="login" />} />
          <Route path="/signup" element={<CredentialsPage mode="signup" />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

const field = (name: string) => screen.getByLabelText(name) as HTMLInputElement;
const type = (name: string, value: string) => fireEvent.change(field(name), { target: { value } });
const submitButton = () => screen.getByRole("button", { name: "가입하고 시작하기" }) as HTMLButtonElement;

function calls(to: string) {
  return (fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls.filter(
    ([url]) => url === to,
  );
}

/** 가입이 가능한 최소 상태로 채운다. */
async function fillValid() {
  screenFor("signup");
  await screen.findByLabelText("비밀번호");
  type("이메일", EMAIL);
  type("비밀번호", PASSWORD);
  type("비밀번호 확인", PASSWORD);
}

beforeEach(() => {
  document.cookie = "__Host-pds_csrf=synthetic-csrf-value; path=/; secure";
  vi.stubGlobal("fetch", signedOut());
});

describe("체크리스트", () => {
  it("타이핑하는 즉시 상태가 바뀐다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    const item = (label: string) => screen.getByText(label).closest("li")!;

    expect(item("8자 이상").className).toBe("unmet");
    type("비밀번호", "diarydiary");
    expect(item("8자 이상").className).toBe("met");
    expect(item("영문 포함").className).toBe("met");
    expect(item("숫자 포함").className).toBe("unmet");

    type("비밀번호", "diarydiary9!");
    expect(item("숫자 포함").className).toBe("met");
    expect(item("특수문자 포함").className).toBe("met");
    expect(item("12자 이상").className).toBe("met");
  });

  it("권장 항목은 권장이라고 적혀 있다", async () => {
    // 다섯 줄이 전부 요구사항으로 읽히면, 특수문자를 강제하지 않기로 한 결정이
    // 화면에서는 강제한 것과 같아진다.
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    expect(screen.getByText("특수문자 포함").closest("li")!.textContent).toContain("권장");
    expect(screen.getByText("영문 포함").closest("li")!.textContent).not.toContain("권장");
  });

  it("로그인 화면에는 없다", async () => {
    screenFor("login");
    await screen.findByLabelText("비밀번호");
    expect(screen.queryByText("8자 이상")).toBeNull();
  });
});

describe("강도 표시", () => {
  it("색만이 아니라 글자로 등급을 말한다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("비밀번호", "12345678");
    expect(screen.getByText(/비밀번호 강도/).textContent).toContain("약함");
    type("비밀번호", "Hello2026");
    expect(screen.getByText(/비밀번호 강도/).textContent).toContain("보통");
    type("비밀번호", "Diary!Cloud2026");
    expect(screen.getByText(/비밀번호 강도/).textContent).toContain("강함");
  });

  it("첫 글자부터 나타나고, 비어 있으면 나타나지 않는다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    expect(screen.queryByText(/비밀번호 강도/)).toBeNull();
    type("비밀번호", "a");
    expect(screen.getByText(/비밀번호 강도/)).toBeTruthy();
  });
});

describe("비밀번호 확인", () => {
  it("입력 전에는 아무 말도 하지 않는다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("비밀번호", PASSWORD);
    expect(screen.queryByText("비밀번호가 일치하지 않습니다.")).toBeNull();
    expect(screen.queryByText("✓ 비밀번호가 일치합니다.")).toBeNull();
  });

  it("불일치와 일치를 각각 말한다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("비밀번호", PASSWORD);
    type("비밀번호 확인", PASSWORD + "오타");
    expect(screen.getByText("비밀번호가 일치하지 않습니다.")).toBeTruthy();
    type("비밀번호 확인", PASSWORD);
    expect(screen.getByText("✓ 비밀번호가 일치합니다.")).toBeTruthy();
  });

  it("로그인 화면에는 없다", async () => {
    // 기억해 내기만 하면 되는 값을 두 번 치게 하는 칸은 틀릴 수만 있다.
    screenFor("login");
    await screen.findByLabelText("비밀번호");
    expect(screen.queryByLabelText("비밀번호 확인")).toBeNull();
  });
});

describe("가입 버튼", () => {
  it("조건을 다 채워야 열린다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    expect(submitButton().disabled).toBe(true);

    type("이메일", "주소가아님");
    type("비밀번호", PASSWORD);
    type("비밀번호 확인", PASSWORD);
    expect(submitButton().disabled).toBe(true); // 이메일 형식

    type("이메일", EMAIL);
    expect(submitButton().disabled).toBe(false);
  });

  it("약함이면 열리지 않는다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("이메일", EMAIL);
    type("비밀번호", "password");
    type("비밀번호 확인", "password");
    expect(screen.getByText(/비밀번호 강도/).textContent).toContain("약함");
    expect(submitButton().disabled).toBe(true);
  });

  it("확인이 다르면 열리지 않는다", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("이메일", EMAIL);
    type("비밀번호", PASSWORD);
    type("비밀번호 확인", PASSWORD + "오타");
    expect(submitButton().disabled).toBe(true);
    fireEvent.click(submitButton());
    await waitFor(() => expect(calls("/api/auth/signup")).toHaveLength(0));
  });

  it("열렸으면 요청이 나간다", async () => {
    await fillValid();
    fireEvent.click(submitButton());
    await waitFor(() => expect(calls("/api/auth/signup")).toHaveLength(1));
  });

  it("로그인 버튼은 이 조건들에 묶이지 않는다", async () => {
    // 오늘의 정책으로 로그인을 막으면 어제의 정책으로 만든 계정이 잠긴다 — T06
    // 자료를 이관받은 계정이 그중 하나다.
    screenFor("login");
    await screen.findByLabelText("비밀번호");
    type("이메일", EMAIL);
    type("비밀번호", "영문도숫자도없는옛비밀번호");
    expect((screen.getByRole("button", { name: "로그인" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("보기/숨김", () => {
  it("칸마다 따로 켜고 끈다", async () => {
    await fillValid();
    expect(field("비밀번호").type).toBe("password");
    expect(field("비밀번호 확인").type).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "비밀번호 보기" }));
    expect(field("비밀번호").type).toBe("text");
    // 확인 칸은 그대로. 한쪽을 드러내는 이유는 대개 가려진 다른 쪽과 맞춰 보기
    // 위해서다.
    expect(field("비밀번호 확인").type).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "비밀번호 확인 보기" }));
    expect(field("비밀번호 확인").type).toBe("text");

    fireEvent.click(screen.getByRole("button", { name: "비밀번호 가리기" }));
    expect(field("비밀번호").type).toBe("password");
    expect(field("비밀번호 확인").type).toBe("text");
  });

  it("폼을 제출하지 않는다", async () => {
    // <form> 안의 <button>은 기본이 type=submit이다. 명시가 없으면 「내가 뭘 쳤나」
    // 보려던 클릭이 가입 시도가 된다. 여기서는 버튼이 이미 열려 있으므로, 제출이
    // 일어났다면 요청이 나간다.
    await fillValid();
    expect(submitButton().disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 보기" }));
    await waitFor(() => expect(calls("/api/auth/signup")).toHaveLength(0));
  });
});

describe("거절당한 뒤", () => {
  it("두 비밀번호를 비우고 다시 가린다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/auth/signup") {
          return new Response(
            JSON.stringify({ error: { message: "이미 가입된 이메일입니다.", details: {} } }),
            { status: 409 },
          );
        }
        return new Response(JSON.stringify({ error: { message: "로그인이 필요합니다." } }), { status: 401 });
      }),
    );

    await fillValid();
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 보기" }));
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 확인 보기" }));
    fireEvent.click(submitButton());

    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("이미 가입된"));
    expect(field("비밀번호").value).toBe("");
    expect(field("비밀번호 확인").value).toBe("");
    // 드러난 채 남은 칸은, 주인이 이미 안 보고 있는 화면에 떠 있는 비밀번호다.
    expect(field("비밀번호").type).toBe("password");
    expect(field("비밀번호 확인").type).toBe("password");
    // 주소는 남긴다. 그건 틀린 부분이 아니었다.
    expect(field("이메일").value).toBe(EMAIL);
  });
});
