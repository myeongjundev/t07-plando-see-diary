/** The signup form's client-side help.
 *
 * None of this is a security boundary -- the server validates the address and
 * the length again, and the confirmation field is never sent anywhere. What is
 * worth testing is that the help does not get in the way: that it cannot create
 * an account with a password its owner mistyped, that the reveal button does
 * not submit the form, and that a failed attempt leaves nothing on screen.
 *
 * Two things are tested by their absence, because they were considered and
 * rejected rather than forgotten: a live "is this address taken" check, which
 * would be an enumeration endpoint, and composition rules, which push people
 * toward shorter and more predictable passwords. See the component's header.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CredentialsPage from "./CredentialsPage";
import { SessionProvider } from "./SessionProvider";

const PASSWORD = "합성-비밀번호-4b2e";

/** Signed out, and every write refused: these tests end at the request. */
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

function calls(to: string) {
  return (fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls.filter(
    ([url]) => url === to,
  );
}

beforeEach(() => {
  document.cookie = "__Host-pds_csrf=synthetic-csrf-value; path=/; secure";
  vi.stubGlobal("fetch", signedOut());
});

describe("the confirmation field", () => {
  it("is on the signup screen", async () => {
    screenFor("signup");
    expect(await screen.findByLabelText("비밀번호 확인")).toBeTruthy();
  });

  it("is not on the login screen", async () => {
    // Confirming a password you are only being asked to remember is a field
    // that can only be got wrong.
    screenFor("login");
    await screen.findByLabelText("비밀번호");
    expect(screen.queryByLabelText("비밀번호 확인")).toBeNull();
  });

  it("stops a mistyped password from becoming an account", async () => {
    // The server cannot catch this: it never sees the second field. If the
    // form submitted anyway, the account would exist with a password its owner
    // has no way to reproduce.
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("이메일", "synthetic@example.invalid");
    type("비밀번호", PASSWORD);
    type("비밀번호 확인", PASSWORD + "오타");

    expect(screen.getByText("비밀번호가 일치하지 않습니다.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "가입하고 시작하기" }));
    await waitFor(() => expect(calls("/api/auth/signup")).toHaveLength(0));
  });

  it("says so when the two match, and lets the request through", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("이메일", "synthetic@example.invalid");
    type("비밀번호", PASSWORD);
    type("비밀번호 확인", PASSWORD);

    expect(screen.getByText("✓ 비밀번호가 일치합니다.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "가입하고 시작하기" }));
    await waitFor(() => expect(calls("/api/auth/signup")).toHaveLength(1));
  });

  it("says nothing until there is something to compare", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("비밀번호", PASSWORD);
    expect(screen.queryByText("비밀번호가 일치하지 않습니다.")).toBeNull();
    expect(screen.queryByText("✓ 비밀번호가 일치합니다.")).toBeNull();
  });
});

describe("the reveal button", () => {
  it("shows and hides both fields together", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    expect(field("비밀번호").type).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "비밀번호 보기" }));
    expect(field("비밀번호").type).toBe("text");
    // Both, or confirming what you typed means reading one row of dots against
    // one row of letters.
    expect(field("비밀번호 확인").type).toBe("text");

    fireEvent.click(screen.getByRole("button", { name: "비밀번호 가리기" }));
    expect(field("비밀번호").type).toBe("password");
  });

  it("does not submit the form", async () => {
    // A <button> inside a <form> defaults to type=submit. Without the explicit
    // type, looking at what you had typed would fire a signup attempt.
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("이메일", "synthetic@example.invalid");
    type("비밀번호", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 보기" }));
    await waitFor(() => expect(calls("/api/auth/signup")).toHaveLength(0));
  });
});

describe("the length hint", () => {
  it("tracks what has been typed", async () => {
    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    expect(screen.getByText("비밀번호는 8자 이상이어야 합니다.")).toBeTruthy();
    type("비밀번호", "짧다");
    expect(screen.getByText("비밀번호는 8자 이상이어야 합니다.")).toBeTruthy();
    type("비밀번호", PASSWORD);
    expect(screen.getByText("✓ 8자 이상")).toBeTruthy();
  });
});

describe("after a refused attempt", () => {
  it("clears both passwords and hides them again", async () => {
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

    screenFor("signup");
    await screen.findByLabelText("비밀번호");
    type("이메일", "taken@example.invalid");
    type("비밀번호", PASSWORD);
    type("비밀번호 확인", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 보기" }));
    fireEvent.click(screen.getByRole("button", { name: "가입하고 시작하기" }));

    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("이미 가입된"));
    expect(field("비밀번호").value).toBe("");
    expect(field("비밀번호 확인").value).toBe("");
    // A revealed field left behind is a password in plain sight on a screen its
    // owner has stopped looking at.
    expect(field("비밀번호").type).toBe("password");
    // The address stays: retyping it is the part that was not the mistake.
    expect(field("이메일").value).toBe("taken@example.invalid");
  });
});
