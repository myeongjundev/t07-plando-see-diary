import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AccountBar from "../../auth/AccountBar";
import { SessionProvider } from "../../auth/SessionProvider";
import SettingsPage from "./SettingsPage";

const ACCOUNT = {
  id: "synthetic",
  email: "portfolio@example.invalid",
  createdAt: "2026-09-04T00:00:00+00:00",
};

function mount() {
  return render(
    <MemoryRouter initialEntries={["/settings"]}>
      <SessionProvider>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/app" element={<p>다이어리 화면</p>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

function mountAccountBar() {
  return render(
    <MemoryRouter initialEntries={["/app"]}>
      <SessionProvider>
        <Routes>
          <Route path="/app" element={<AccountBar />} />
          <Route path="/settings" element={<p>설정 화면</p>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url === "/api/auth/me") {
      return new Response(JSON.stringify({ user: ACCOUNT }), { status: 200 });
    }
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }));
});

describe("설정 화면", () => {
  it("프로필 · 내 데이터 · 보안 및 계정을 한곳에 모은다", async () => {
    mount();

    expect(await screen.findByRole("heading", { name: "설정" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "프로필" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "내 자료 내보내기" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "보안 및 계정" })).toBeTruthy();
    expect(screen.getAllByText(ACCOUNT.email)).toHaveLength(2);
    expect(screen.getByText("2026년 9월 4일")).toBeTruthy();
  });

  it("상단 계정 메뉴에서 다이어리로 돌아갈 수 있다", async () => {
    mount();

    const link = await screen.findByRole("link", { name: "다이어리" });
    expect(link.getAttribute("href")).toBe("/app");
  });

  it("다이어리 상단 계정 메뉴에서 설정으로 들어갈 수 있다", async () => {
    mountAccountBar();

    const link = await screen.findByRole("link", { name: "설정" });
    expect(link.getAttribute("href")).toBe("/settings");
  });
});
