/** 계정 화면. T07-C114, C134.
 *
 * 두 폼 모두 되돌리기 어려운 일을 한다 — 하나는 다른 기기를 전부 끊고, 하나는 자료를
 * 영구히 지운다. 그래서 검사도 「눌리는가」보다 **「눌리지 않아야 할 때 눌리지 않는가」**
 * 쪽이 많다.
 *
 * 서버가 같은 것을 다시 확인한다(`app/api/account.py`, `app/api/auth.py`). 여기 어떤
 * 것도 보안 경계가 아니다.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AccountPanel from "./AccountPanel";
import { SessionProvider } from "../../auth/SessionProvider";

const ACCOUNT = { id: "synthetic", email: "diarist@example.invalid", createdAt: "2026-09-04T00:00:00+00:00" };
const CURRENT = "합성-현재-비밀번호-2c40";
const NEXT = "합성-새-비밀번호-8d31";

/** Signed in, and every write succeeds unless a test says otherwise. */
function server(overrides: Record<string, () => Response> = {}) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url}`;
    if (overrides[key]) return overrides[key]();
    if (url === "/api/auth/me") {
      return new Response(JSON.stringify({ user: ACCOUNT }), { status: 200 });
    }
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  });
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/app"]}>
      <SessionProvider>
        <Routes>
          <Route path="/app" element={<AccountPanel />} />
          <Route path="/login" element={<p>로그인 화면</p>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

const field = (name: string | RegExp) => screen.getByLabelText(name) as HTMLInputElement;
const type = (name: string | RegExp, value: string) =>
  fireEvent.change(field(name), { target: { value } });
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

function calls(key: string) {
  return (fetch as unknown as { mock: { calls: [string, RequestInit?][] } }).mock.calls.filter(
    ([url, init]) => `${(init?.method ?? "GET").toUpperCase()} ${url}` === key,
  );
}

async function ready() {
  mount();
  await screen.findByLabelText("현재 비밀번호");
}

beforeEach(() => {
  document.cookie = "__Host-pds_csrf=synthetic-csrf-value; path=/; secure";
  vi.stubGlobal("fetch", server());
});

describe("비밀번호 변경", () => {
  it("현재 비밀번호 · 강도 · 일치가 모두 갖춰져야 눌린다", async () => {
    await ready();
    expect(button("비밀번호 바꾸기").disabled).toBe(true);

    type("새 비밀번호", NEXT);
    type("새 비밀번호 확인", NEXT);
    expect(button("비밀번호 바꾸기").disabled).toBe(true); // 현재 비밀번호가 없다

    type("현재 비밀번호", CURRENT);
    expect(button("비밀번호 바꾸기").disabled).toBe(false);
  });

  it("새 비밀번호가 약하면 눌리지 않는다", async () => {
    // 가입과 같은 판정을 쓴다. 다른 문으로 들어왔다고 규칙이 느슨해지면 그건 두
    // 번째 문이 아니라 우회로다.
    await ready();
    type("현재 비밀번호", CURRENT);
    type("새 비밀번호", "password");
    type("새 비밀번호 확인", "password");
    expect(screen.getByText(/비밀번호 강도/).textContent).toContain("약함");
    expect(button("비밀번호 바꾸기").disabled).toBe(true);
  });

  it("확인이 다르면 눌리지 않는다", async () => {
    await ready();
    type("현재 비밀번호", CURRENT);
    type("새 비밀번호", NEXT);
    type("새 비밀번호 확인", NEXT + "오타");
    expect(screen.getByText("비밀번호가 일치하지 않습니다.")).toBeTruthy();
    expect(button("비밀번호 바꾸기").disabled).toBe(true);
  });

  it("다른 기기가 끊긴다는 것을 미리 말한다", async () => {
    await ready();
    expect(screen.getByText(/다른 기기의 로그인이 모두 해제됩니다/)).toBeTruthy();
  });

  it("성공하면 세 칸을 비우고 결과를 말한다", async () => {
    await ready();
    type("현재 비밀번호", CURRENT);
    type("새 비밀번호", NEXT);
    type("새 비밀번호 확인", NEXT);
    fireEvent.click(button("비밀번호 바꾸기"));

    await waitFor(() => expect(calls("POST /api/auth/password")).toHaveLength(1));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("바꿨습니다"));
    expect(field("현재 비밀번호").value).toBe("");
    expect(field("새 비밀번호").value).toBe("");
    expect(field("현재 비밀번호").type).toBe("password");
  });

  it("서버가 거절하면 그 문구를 그대로 보여 준다", async () => {
    vi.stubGlobal("fetch", server({
      "POST /api/auth/password": () =>
        new Response(
          JSON.stringify({ error: { message: "현재 비밀번호가 올바르지 않습니다.", details: {} } }),
          { status: 401 },
        ),
    }));
    await ready();
    type("현재 비밀번호", "틀린-비밀번호-1234");
    type("새 비밀번호", NEXT);
    type("새 비밀번호 확인", NEXT);
    fireEvent.click(button("비밀번호 바꾸기"));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("현재 비밀번호가 올바르지 않습니다."),
    );
  });
});

describe("계정 삭제", () => {
  it("무엇이 지워지는지 화면에 적혀 있다 (C134)", async () => {
    await ready();
    const warning = screen.getByText(/되돌릴 수 없습니다/);
    for (const item of ["계획", "할 일", "실행 기록", "회고"]) {
      expect(warning.textContent).toContain(item);
    }
  });

  it("비밀번호와 확인 문구가 모두 있어야 눌린다", async () => {
    await ready();
    expect(button("계정과 모든 자료 삭제").disabled).toBe(true);

    type("비밀번호", CURRENT);
    expect(button("계정과 모든 자료 삭제").disabled).toBe(true); // 확인 문구가 없다

    type(/확인을 위해/, "계정 삭재");
    expect(button("계정과 모든 자료 삭제").disabled).toBe(true); // 오타

    type(/확인을 위해/, "계정 삭제");
    expect(button("계정과 모든 자료 삭제").disabled).toBe(false);
  });

  it("삭제하면 로그인 화면으로 나간다", async () => {
    await ready();
    type("비밀번호", CURRENT);
    type(/확인을 위해/, "계정 삭제");
    fireEvent.click(button("계정과 모든 자료 삭제"));

    await waitFor(() => expect(calls("DELETE /api/account")).toHaveLength(1));
    await waitFor(() => expect(screen.getByText("로그인 화면")).toBeTruthy());
  });

  it("거절당하면 화면에 남고 비밀번호만 비운다", async () => {
    // 삭제가 실패했는데 로그인 화면으로 나가면, 지워졌는지 아닌지 알 수 없다.
    vi.stubGlobal("fetch", server({
      "DELETE /api/account": () =>
        new Response(
          JSON.stringify({ error: { message: "비밀번호가 올바르지 않습니다.", details: {} } }),
          { status: 401 },
        ),
    }));
    await ready();
    type("비밀번호", "틀린-비밀번호-1234");
    type(/확인을 위해/, "계정 삭제");
    fireEvent.click(button("계정과 모든 자료 삭제"));

    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("올바르지 않습니다"));
    expect(screen.queryByText("로그인 화면")).toBeNull();
    expect(field("비밀번호").value).toBe("");
  });
});
