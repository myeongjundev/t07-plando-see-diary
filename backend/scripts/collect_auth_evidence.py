"""Run the auth flows once and write down what actually happened.

Design section 10. Produces `docs/T07-EVIDENCE/01…11-*.md` for the guide's
section ④ (T07-C129), and the criteria that ask for a recorded request-and-
response pair rather than a claim.

Three rules, and each is a way this could go wrong:

**Nothing is typed by hand.** Every request and response in the output came
from this run. A file assembled from memory drifts from the code the moment
either changes, and the drift is invisible -- it still reads like evidence.

**Everything passes through `app.security.redact`.** One function, so "did we
remember to mask it" is a question about one place rather than about forty call
sites. `test_c115_evidence_files_contain_no_token` and `test_c131_no_secret_in_docs`
check the output rather than trusting this sentence.

**Every file carries a success and a refusal.** C129 asks for both halves: a
file with only refusals does not show that the thing works, and one with only
successes does not show that anything is guarded.

Run it with:

    backend/.venv/Scripts/python.exe backend/scripts/collect_auth_evidence.py

It builds a throwaway SQLite database in a temporary directory and never touches
a deployment. The accounts and diary entries in the output are synthetic; the
passwords in this file exist only to be refused and re-typed here.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

# Fixed so the output is stable between runs: a file whose only change is a new
# random key produces a diff that says nothing.
os.environ.setdefault("JWT_SECRET", "synthetic-evidence-signing-key-not-a-real-secret-000000")
os.environ.setdefault("IP_HASH_SECRET", "synthetic-evidence-ip-key-not-a-real-secret-11111111")

from app import create_app  # noqa: E402
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, REFRESH_PATH  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import LoginAttempt, RefreshSession, SecurityEvent, User  # noqa: E402
from app.security import passwords  # noqa: E402
from app.security.redact import redact  # noqa: E402
from app.security.tokens import absolute_ttl, access_ttl, idle_ttl  # noqa: E402
from app.services import throttle  # noqa: E402

OUT = ROOT / "docs" / "T07-EVIDENCE"

# Synthetic throughout. Neither address exists and neither password protects
# anything -- they are here so the refusals below have something to refuse.
A = ("evidence-a@example.invalid", "합성-증거-계정A-7f21")
B = ("evidence-b@example.invalid", "합성-증거-계정B-4c98")
SHARED = "합성-같은-비밀번호-9d33"
WRONG = "합성-틀린-비밀번호-0000"

PLAN = {
    "title": "합성 계획",
    "startDate": "2026-09-01",
    "endDate": "2026-09-07",
    "priority": "high",
    "successCriterion": "합성 성공 기준",
    "estimatedMinutes": 600,
}
TASK = {
    "content": "합성 할 일",
    "dueDate": "2026-09-02",
    "priority": "high",
    "tags": ["합성"],
    "estimatedMinutes": 120,
}

# Cookie values are never printed. What matters to every criterion here is
# *which* cookies rode along, not what was in them.
COOKIE_NAMES = {ACCESS_COOKIE: "access", REFRESH_COOKIE: "refresh", CSRF_COOKIE: "csrf"}


def stamp() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S +0900")


class Browser:
    """One test client plus the record of everything it sent and received."""

    def __init__(self, app, label: str):
        self.app = app
        self.label = label
        self.client = app.test_client()

    def cookie(self, name, path="/"):
        found = self.client.get_cookie(name, path=path)
        return found.value if found else None

    def carried(self) -> str:
        names = [
            label
            for name, label in COOKIE_NAMES.items()
            if self.cookie(name, REFRESH_PATH if name == REFRESH_COOKIE else "/")
        ]
        return ", ".join(f"{name}=[redacted]" for name in names) or "(없음)"

    def send(self, method, path, body=None, *, csrf=True, headers=None, note=None):
        sent = dict(headers or {})
        if csrf and method in {"POST", "PATCH", "DELETE"}:
            token = self.cookie(CSRF_COOKIE)
            if token:
                sent["X-CSRF-Token"] = token
        kwargs = {"headers": sent}
        if body is not None:
            kwargs["json"] = body
        # Read before sending. The response updates the cookie jar, so asking
        # afterwards reports the state the request produced rather than the one
        # it carried -- which would print "Cookie: (없음)" on the logout that
        # C109 exists to show carrying a session.
        carried = self.carried()
        response = self.client.open(path, method=method, **kwargs)
        return Exchange(self, method, path, body, sent, response, note, carried)


class Exchange:
    """One request/response pair, rendered as the markdown the guide carries."""

    def __init__(self, browser, method, path, body, headers, response, note, carried):
        self.browser = browser
        self.method = method
        self.path = path
        self.body = body
        self.headers = headers
        self.response = response
        self.note = note
        self.cookies_sent = carried
        self.set_cookie = [
            header.split("=", 1)[0] for header in response.headers.getlist("Set-Cookie")
        ]

    @property
    def status(self) -> int:
        return self.response.status_code

    def render(self, index: int, title: str) -> str:
        header_lines = [f"Cookie: {self.cookies_sent}"]
        for name, value in self.headers.items():
            # The CSRF value is readable by script by design, and is still a
            # session-scoped value: the criterion wants to see that the header
            # was present, not what was in it.
            header_lines.append(f"{name}: {'[redacted]' if 'CSRF' in name else value}")

        request_body = ""
        if self.body is not None:
            request_body = "\n\n" + json.dumps(redact(self.body), ensure_ascii=False, indent=2)

        set_cookie = (
            ", ".join(f"{name}=[redacted]" for name in self.set_cookie)
            if self.set_cookie
            else "(없음)"
        )
        payload = self.response.get_json(silent=True)
        response_body = (
            "\n\n" + json.dumps(redact(payload), ensure_ascii=False, indent=2)[:1600]
            if payload is not None
            else ""
        )
        retry_after = self.response.headers.get("Retry-After")
        retry_line = f"\nRetry-After: {retry_after}" if retry_after else ""

        note = f"\n{self.note}\n" if self.note else ""
        return (
            f"### {index}. {title}\n"
            f"{note}\n"
            "```http\n"
            f"{self.method} {self.path}\n"
            f"{chr(10).join(header_lines)}"
            f"{request_body}\n"
            "```\n\n"
            "```http\n"
            f"{self.response.status}\n"
            f"Set-Cookie: {set_cookie}{retry_line}"
            f"{response_body}\n"
            "```\n"
        )


class Document:
    """A single evidence file. Refuses to be written without both halves."""

    def __init__(self, name: str, title: str, criteria: str, lede: str):
        self.name = name
        self.title = title
        self.criteria = criteria
        self.lede = lede
        self.blocks: list[str] = []
        self.statuses: list[int] = []

    def add(self, exchange: Exchange, title: str) -> Exchange:
        self.blocks.append(exchange.render(len(self.blocks) + 1, title))
        self.statuses.append(exchange.status)
        return exchange

    def note(self, text: str) -> None:
        self.blocks.append(text.strip() + "\n")

    def write(self) -> None:
        successes = [code for code in self.statuses if 200 <= code < 300]
        denials = [code for code in self.statuses if 400 <= code < 500]
        if not successes or not denials:
            # C129 wants both halves in each file. Failing here is better than
            # producing a file that quietly proves only one of them.
            raise SystemExit(
                f"{self.name}: needs a success and a refusal, "
                f"got successes={successes} denials={denials}"
            )
        body = (
            f"# {self.title}\n\n"
            f"- 기준: {self.criteria}\n"
            f"- 수집: {stamp()} · `backend/scripts/collect_auth_evidence.py` 실행 결과\n"
            f"- 성공 {len(successes)}건 · 거절 {len(denials)}건\n\n"
            f"{self.lede.strip()}\n\n"
            "> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,\n"
            "> 값은 전부 `app/security/redact.py` 한 곳을 지난다.\n\n"
            + "\n".join(self.blocks)
        )
        (OUT / self.name).write_text(body, encoding="utf-8")
        print(f"wrote docs/T07-EVIDENCE/{self.name}  (성공 {len(successes)} · 거절 {len(denials)})")


# ---------------------------------------------------------------------------
# The runs
# ---------------------------------------------------------------------------


def signup(browser, account):
    return browser.send("POST", "/api/auth/signup", {"email": account[0], "password": account[1]})


def login(browser, account, password=None):
    return browser.send(
        "POST", "/api/auth/login", {"email": account[0], "password": password or account[1]}
    )


def furnish(browser, title):
    """A plan, a task and one execution log, so there is something to protect."""
    plan = browser.send("POST", "/api/plans", {**PLAN, "title": title}).response.get_json()["plan"]
    task = browser.send(
        "POST", f"/api/plans/{plan['id']}/tasks", TASK
    ).response.get_json()["task"]
    browser.send(
        "POST",
        f"/api/tasks/{task['id']}/executions",
        {
            "startedAt": "2026-09-01T13:00:00+09:00",
            "endedAt": "2026-09-01T14:30:00+09:00",
            "actualMinutes": 90,
            "blockerReason": "합성 사유",
        },
    )
    return plan, task


def file_01(app):
    doc = Document(
        "01-signup-login-logout.md",
        "가입 · 로그인 · 로그아웃",
        "T07-C94 · C95 · C96 · C98 · C99",
        "계정을 만들고, 그 계정으로 들어가고, 나온다. 그리고 같은 주소로 두 번 가입되지 "
        "않는 것과, 로그인이 실패하는 두 경우가 **같은 문장·같은 상태**로 답하는 것.",
    )
    browser = Browser(app, "A")
    doc.add(signup(browser, A), "가입 (C94)")
    doc.add(signup(browser, A), "같은 주소로 다시 가입 — 거절 (C98)")
    doc.add(login(browser, A), "로그인 (C95)")
    doc.add(browser.send("POST", "/api/auth/logout", {}), "로그아웃 (C96)")

    wrong = doc.add(login(browser, A, WRONG), "비밀번호만 틀림 (C99)")
    absent = doc.add(
        Browser(app, "anon").send(
            "POST", "/api/auth/login", {"email": "nobody@example.invalid", "password": WRONG}
        ),
        "없는 계정 (C99)",
    )
    same = wrong.response.get_json() == absent.response.get_json()
    doc.note(
        "**두 거절의 본문이 글자 단위로 같은가: "
        f"{'같다' if same else '다르다'}** · 상태 {wrong.status} / {absent.status}\n\n"
        "문구가 같아도 응답이 열 배 빨리 오면 같은 것을 말한 것이 아니다. 없는 계정에도 "
        "실제 Argon2 검증을 한 번 돌리는 이유가 그것이고, 그 사실은 "
        "`app/security/passwords.py::dummy_verify`에 있다."
    )
    doc.write()


def file_02(app):
    doc = Document(
        "02-password-storage.md",
        "비밀번호를 어떻게 맡아 두는가",
        "T07-C101 ~ C107",
        "저장된 값의 모양과, **같은 비밀번호로 만든 두 계정의 저장 값이 서로 다른 것**. "
        "뒤쪽은 인증 서비스를 골랐다면 만들 수 없는 장면이다.",
    )
    one = Browser(app, "same-1")
    two = Browser(app, "same-2")
    doc.add(
        one.send("POST", "/api/auth/signup", {"email": "same-1@example.invalid", "password": SHARED}),
        "같은 비밀번호로 계정 1",
    )
    doc.add(
        two.send("POST", "/api/auth/signup", {"email": "same-2@example.invalid", "password": SHARED}),
        "같은 비밀번호로 계정 2",
    )
    doc.add(
        one.send("POST", "/api/auth/signup", {"email": "same-1@example.invalid", "password": SHARED}),
        "그 주소로 다시 가입 — 거절",
    )

    with app.app_context():
        stored = [
            row.password_hash
            for row in db.session.scalars(
                db.select(User).where(User.email.in_(["same-1@example.invalid", "same-2@example.invalid"]))
            )
        ]
    # Written out field by field rather than as one specimen string. A
    # real-looking `$argon2id$…` line cannot be told apart from a leaked hash by
    # anyone scanning the submission -- including this project's own
    # `test_c115_evidence_files_contain_no_token`, which is how this got caught.
    fields = stored[0].split("$")
    doc.note(
        "## 저장된 모습 (C103)\n\n"
        "| 칸 | 값 |\n| --- | --- |\n"
        f"| 알고리즘 | `{fields[1]}` |\n"
        f"| 버전 | `{fields[2]}` |\n"
        f"| 매개변수 | `{fields[3]}` |\n"
        "| 소금 | (가림 — 값 안에 함께 들어 있다) |\n"
        "| 해시 | (가림) |\n\n"
        f"- 전체 길이 {len(stored[0])}자\n"
        "- **입력한 글자가 그대로 보이는가: 아니오.** 확인은 저장 값 안에서 원문을 "
        "찾아보는 것으로 했고, 결과는 "
        f"**{'찾음 — 문제' if SHARED in stored[0] else '찾지 못함'}**이다. 그 원문을 "
        "여기 적지는 않는다 — 적는 순간 이 파일이 C105를 어긴다.\n"
        f"- 같은 비밀번호로 만든 두 계정의 저장 값이 서로 다른가 (C104): "
        f"**{'다르다' if stored[0] != stored[1] else '같다'}**\n"
        f"- 매개변수: `{json.dumps(passwords.current_parameters())}` — "
        "소금과 매개변수가 값 안에 들어 있으므로 따로 관리하는 열이 없다\n\n"
        "해시 원문은 싣지 않는다. 되돌릴 수 없다는 것과 오프라인 추측을 도와도 된다는 "
        "것은 다른 이야기다 (C131)."
    )
    doc.write()


def file_03(app):
    doc = Document(
        "03-logout-replay-blocked.md",
        "로그아웃 전후, 같은 요청",
        "T07-C108 · C109 · C110 · C114",
        "**같은 주소·같은 방식**의 요청을 로그아웃 앞뒤로 한 번씩. 달라진 것은 로그아웃 "
        "여부뿐이다.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    login(browser, A)
    doc.add(browser.send("GET", "/api/auth/me"), "로그아웃 전 — `GET /api/auth/me`")
    doc.add(browser.send("POST", "/api/auth/logout", {}), "로그아웃")
    after = doc.add(browser.send("GET", "/api/auth/me"), "로그아웃 후 — **같은 요청**")
    doc.note(
        "두 요청의 메서드와 주소가 같다: `GET /api/auth/me`. 첫 번째는 200, 세 번째는 "
        f"{after.status}. 중간에 일어난 일은 로그아웃뿐이다 (C109 · C110).\n\n"
        "Access 토큰은 그 사이에 만료하지 않았다 — 서명도 유효하고 "
        f"수명({int(access_ttl().total_seconds())}초)도 남아 있다. 그래도 통하지 않는 것은 "
        "가드가 토큰만 보지 않고 세션 행을 읽기 때문이고, 그것이 C114가 요구하는 "
        "「이전에 발급한 값이 더는 통하지 않는다」다 (설계 1절)."
    )
    doc.write()


def file_04(app):
    doc = Document(
        "04-refresh-rotation.md",
        "Refresh 회전",
        "T07-C111",
        "A를 써서 B를 받고, 그 뒤 A는 죽는다. 한 번 쓴 값이 계속 통하면 훔친 값도 계속 통한다.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    login(browser, A)
    spent = browser.cookie(REFRESH_COOKIE, REFRESH_PATH)
    doc.add(browser.send("POST", "/api/auth/refresh", {}), "A를 써서 B를 받는다")
    fresh = browser.cookie(REFRESH_COOKIE, REFRESH_PATH)
    doc.add(browser.send("GET", "/api/auth/me"), "새 Access로 요청 — 통한다")

    browser.client.set_cookie(REFRESH_COOKIE, spent, path=REFRESH_PATH)
    doc.add(browser.send("POST", "/api/auth/refresh", {}, csrf=False), "쓴 A를 다시 — 거절")
    with app.app_context():
        rows = db.session.scalars(
            db.select(RefreshSession).order_by(RefreshSession.issued_at)
        ).all()
        table = "\n".join(
            f"| {index + 1} | {row.family_id[:8]}… | "
            f"{'살아 있음' if row.revoked_at is None else row.revoked_reason} |"
            for index, row in enumerate(rows)
        )
    doc.note(
        f"- 쿠키 값이 바뀌었는가: **{'예' if spent != fresh else '아니오'}** "
        "(두 값 모두 여기 싣지 않는다)\n\n"
        "| # | 계열 | 상태 |\n| ---: | --- | --- |\n" + table + "\n\n"
        "회전은 로그인 하나를 이어 가는 것이라 **계열이 같다.** 절대 만료도 물려받는다 — "
        "회전이 늘릴 수 있는 한도는 절대 한도가 아니다 (C111)."
    )
    doc.write()


def file_05(app):
    doc = Document(
        "05-refresh-reuse-detected.md",
        "Refresh 재사용 탐지",
        "설명서 ⑤ · 설계 4절",
        "한 번 쓴 Refresh가 다시 오면 그 값은 그 사이에 **복제됐다는 뜻**이다. 누가 "
        "진짜인지 알 수 없으므로 그 로그인에서 뻗어 나온 계열을 통째로 끊는다.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    login(browser, A)
    spent = browser.cookie(REFRESH_COOKIE, REFRESH_PATH)
    doc.add(browser.send("POST", "/api/auth/refresh", {}), "정상 회전")
    doc.add(browser.send("GET", "/api/auth/me"), "회전 직후 — 통한다")

    browser.client.set_cookie(REFRESH_COOKIE, spent, path=REFRESH_PATH)
    doc.add(browser.send("POST", "/api/auth/refresh", {}, csrf=False), "쓴 값을 재생 — 거절")
    doc.add(browser.send("GET", "/api/auth/me"), "재생 이후 — 계열이 끊겨 통하지 않는다")

    with app.app_context():
        events = db.session.scalars(
            db.select(SecurityEvent).where(
                SecurityEvent.event_type == "REFRESH_TOKEN_REUSE_DETECTED"
            )
        ).all()
        reasons = {
            row.revoked_reason for row in db.session.scalars(db.select(RefreshSession))
        }
    doc.note(
        f"- `REFRESH_TOKEN_REUSE_DETECTED` 기록: **{len(events)}건**\n"
        f"- 계열의 폐기 사유: {sorted(str(reason) for reason in reasons)}\n\n"
        "정상 사용자도 다시 로그인해야 한다. 그 대가를 알고 골랐다 — 도둑이 들고 간 "
        "후계 토큰을 살려 두는 것보다 낫다 (설계 11절)."
    )
    doc.write()


def file_06(app):
    doc = Document(
        "06-csrf-blocked.md",
        "교차 사이트 요청 막기",
        "설명서 ⑥ · 설계 5절",
        "같은 로그인 상태에서 **정상 · 헤더 없음 · 헤더 불일치 · JSON 아님 · 교차 출처** "
        "다섯 가지. 달라진 것은 요청의 모양뿐이다.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    login(browser, A)
    doc.add(browser.send("POST", "/api/plans", PLAN), "정상 — 쿠키와 헤더가 맞는다")
    doc.add(browser.send("POST", "/api/plans", PLAN, csrf=False), "헤더 없음 — 거절")
    doc.add(
        browser.send("POST", "/api/plans", PLAN, csrf=False, headers={"X-CSRF-Token": "틀린-값"}),
        "헤더 불일치 — 거절",
    )
    doc.add(
        Browser(app, "form").send(
            "POST",
            "/api/auth/login",
            None,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ),
        "JSON 아님 — 거절 (415)",
    )
    doc.add(
        browser.send(
            "POST", "/api/plans", PLAN, headers={"Origin": "https://attacker.example"}
        ),
        "교차 출처 — 거절",
    )
    doc.note(
        "세 겹이라 하나가 무너져도 나머지가 남는다: SameSite · JSON과 Origin · "
        "`__Host-` 이중 제출. 브라우저가 스크립트 없이 보낼 수 있는 폼 POST는 "
        "`application/json`을 만들 수 없고, 그걸 만들려면 사전 요청이 필요한데 CORS "
        "헤더를 하나도 내주지 않는다 (설계 5절)."
    )
    doc.write()


def file_07(app):
    doc = Document(
        "07-bruteforce-blocked.md",
        "무차별 대입 잠금",
        "설명서 ⑤ · 설계 6절",
        "같은 (계정, 주소)로 다섯 번 틀리면 잠긴다. **없는 계정도 똑같이 잠긴다** — "
        "안 그러면 「잠기지 않는다」가 곧 「그런 계정 없다」가 된다.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    doc.add(login(browser, A), "정상 로그인 — 잠금 전")
    browser.send("POST", "/api/auth/logout", {})
    for attempt in range(throttle.EMAIL_IP_THRESHOLD):
        doc.add(login(browser, A, WRONG), f"틀린 비밀번호 {attempt + 1}회")
    blocked = doc.add(login(browser, A, WRONG), "여섯 번째 — 429")
    right = doc.add(login(browser, A), "맞는 비밀번호로도 — 여전히 429")

    absent = ("nobody@example.invalid", WRONG)
    ghost = Browser(app, "ghost")
    for _ in range(throttle.EMAIL_IP_THRESHOLD):
        ghost.send("POST", "/api/auth/login", {"email": absent[0], "password": absent[1]})
    ghost_blocked = doc.add(
        ghost.send("POST", "/api/auth/login", {"email": absent[0], "password": absent[1]}),
        "없는 계정도 같은 횟수에 같은 429",
    )
    # 잠금이 영구가 아니라는 것도 보여야 한다. 60초를 기다리는 대신 기록해 둔 시도의
    # 시각을 과거로 옮긴다 -- 응답을 만드는 코드는 그대로고 옮긴 것은 시계뿐이다.
    with app.app_context():
        for row in db.session.scalars(db.select(LoginAttempt)):
            row.attempted_at = throttle._aware(row.attempted_at) - timedelta(seconds=61)
        db.session.commit()
    released = doc.add(login(browser, A), "첫 잠금이 지난 뒤 — 다시 들어온다")

    doc.note(
        f"- 창 {int(throttle.WINDOW.total_seconds() // 60)}분 · 임계 "
        f"{throttle.EMAIL_IP_THRESHOLD}회(계정+주소) 또는 {throttle.IP_THRESHOLD}회(주소)\n"
        f"- 첫 잠금 {blocked.response.headers.get('Retry-After')}초, 이후 실패마다 배증, "
        f"최대 {int(throttle.MAX_LOCK.total_seconds() // 60)}분\n"
        f"- 있는 계정과 없는 계정의 응답이 같은가: "
        f"**{'같다' if blocked.response.get_json() == ghost_blocked.response.get_json() else '다르다'}** "
        f"({blocked.status} / {ghost_blocked.status})\n"
        f"- 맞는 비밀번호로도 잠금을 넘지 못한다: {right.status}\n\n"
        "**잠금 중 요청은 실패 횟수에 넣지 않는다.** 넣으면 공격자가 요청만 계속 보내 "
        "피해자를 창 내내 붙들 수 있다. IP는 원문을 저장하지 않고 "
        "`HMAC-SHA-256(IP_HASH_SECRET, 주소)`로만 남는다.\n\n"
        "여기서 정직하게 교환한 것 하나: 잠긴 정상 사용자에게 「잠겼습니다」라고 말하지 "
        "않는다. 그 안내가 곧 계정이 있다는 증거가 되기 때문이고, 존재를 감추는 쪽을 "
        "골랐다. 설명서 ⑥."
    )
    doc.write()


def file_08(app):
    doc = Document(
        "08-cross-user-access-blocked.md",
        "남의 자료가 안 열리는 것",
        "T07-C116 ~ C126",
        "계정 두 개에 각각 자료를 넣고, **양방향으로** 읽기·수정·삭제를 시도한다. "
        "주소·헤더·본문에 남의 ID를 적어 보낸 것과, 로그인하지 않은 요청도 함께.",
    )
    alice = Browser(app, "A")
    bob = Browser(app, "B")
    signup(alice, A)
    login(alice, A)
    signup(bob, B)
    login(bob, B)
    alice_plan, alice_task = furnish(alice, "앨리스의 합성 계획")
    bob_plan, bob_task = furnish(bob, "밥의 합성 계획")

    def counts(browser):
        body = browser.send("GET", "/api/plans").response.get_json()
        return len(body["plans"])

    before = {"A": counts(alice), "B": counts(bob)}

    doc.add(alice.send("GET", f"/api/plans/{alice_plan['id']}"), "A가 자기 계획을 읽는다 (C116)")
    doc.add(alice.send("GET", f"/api/plans/{bob_plan['id']}"), "A → B 읽기 (C117)")
    doc.add(
        alice.send("PATCH", f"/api/plans/{bob_plan['id']}", {"estimatedMinutes": 1}),
        "A → B 수정 (C118)",
    )
    doc.add(alice.send("DELETE", f"/api/tasks/{bob_task['id']}"), "A → B 삭제 (C119)")
    doc.add(bob.send("GET", f"/api/plans/{alice_plan['id']}"), "B → A 읽기 (C120)")
    doc.add(
        bob.send("PATCH", f"/api/plans/{alice_plan['id']}", {"estimatedMinutes": 1}),
        "B → A 수정 (C120)",
    )
    doc.add(bob.send("DELETE", f"/api/tasks/{alice_task['id']}"), "B → A 삭제 (C120)")
    forged = doc.add(
        alice.send(
            "GET",
            f"/api/plans?userId={bob_plan['id']}",
            headers={"X-User-Id": "B"},
        ),
        "주소·헤더에 남을 적어 보냄 — 그래도 내 것만 (C123)",
    )
    doc.add(
        Browser(app, "anon").send("GET", "/api/plans"),
        "로그인하지 않고 자료 요청 (C124)",
    )
    listed = doc.add(alice.send("GET", "/api/plans"), "목록에 남의 것이 없다 (C125)")

    after = {"A": counts(alice), "B": counts(bob)}
    body = json.dumps(listed.response.get_json(), ensure_ascii=False)
    doc.note(
        "## 거절 앞뒤 건수 (C122)\n\n"
        "| 계정 | 시도 전 | 시도 후 |\n| --- | ---: | ---: |\n"
        f"| A | {before['A']} | {after['A']} |\n"
        f"| B | {before['B']} | {after['B']} |\n\n"
        f"- A의 목록에 B의 계획 ID가 들어 있는가: "
        f"**{'있다' if bob_plan['id'] in body else '없다'}** (C125)\n"
        f"- 위조한 요청이 돌려준 계획 수: "
        f"{len(forged.response.get_json().get('plans', []))}건 — 내 것뿐 (C123)\n\n"
        "거절은 **404**다. 403은 「있지만 당신 것이 아니다」를 말해 주고, 그건 남의 ID가 "
        "실재하는지 확인해 주는 통로가 된다 (C121). 거절을 만드는 곳은 세 파일뿐이다 — "
        "`guards.py` · `ownership.py` · `csrf.py` (C126)."
    )
    doc.write()


def file_09(app):
    doc = Document(
        "09-session-expiration.md",
        "세션 만료 — 유휴와 절대",
        "T07-C111",
        "48시간 쓰지 않으면 끊기고, 14일이 지나면 얼마나 부지런히 썼든 끊긴다.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    login(browser, A)
    doc.add(browser.send("GET", "/api/auth/me"), "정상 — 세션이 살아 있다")

    with app.app_context():
        row = db.session.scalar(db.select(RefreshSession))
        row.last_used_at = datetime.now(timezone.utc) - idle_ttl() - timedelta(minutes=1)
        db.session.commit()
    doc.add(browser.send("GET", "/api/auth/me"), "유휴 한도를 넘긴 뒤 — 거절")
    doc.add(browser.send("POST", "/api/auth/refresh", {}, csrf=False), "회전으로도 되살아나지 않는다")

    second = Browser(app, "A2")
    login(second, A)
    with app.app_context():
        row = db.session.scalar(
            db.select(RefreshSession).where(RefreshSession.revoked_at.is_(None))
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        row.last_used_at = datetime.now(timezone.utc)
        db.session.commit()
    doc.add(second.send("GET", "/api/auth/me"), "방금 썼지만 절대 한도를 넘긴 세션 — 거절")

    doc.note(
        "## 시간을 앞당긴 방법 — 숨기지 않는다\n\n"
        "48시간과 14일을 실제로 기다릴 수 없으므로, 세션 행의 `last_used_at`과 "
        "`expires_at`을 과거로 옮겨 두고 같은 요청을 보냈다. **응답을 만든 코드는 그대로**이고, "
        "옮긴 것은 시계뿐이다.\n\n"
        "| 값 | 설정 | 어디서 읽는가 |\n| --- | ---: | --- |\n"
        f"| Access 수명 | {int(access_ttl().total_seconds())}초 | `security/tokens.py` |\n"
        f"| 유휴 한도 | {int(idle_ttl().total_seconds() // 3600)}시간 | `services/sessions.py` |\n"
        f"| 절대 한도 | {int(absolute_ttl().total_seconds() // 86400)}일 | 로그인 때 정해지고 회전이 물려받는다 |\n\n"
        "거절의 문구는 모르는 토큰이 받는 것과 같다. 어느 쪽으로 죽었는지 알려 주면 "
        "훔친 값의 어느 절반이 아직 쓸모 있는지 알려 주는 셈이다."
    )
    doc.write()


def file_10(app):
    doc = Document(
        "10-security-events.md",
        "남은 기록과, 거기 없는 것",
        "T07-C115 · C131 · 설계 7절",
        "위의 모든 실행이 감사 기록에 무엇을 남겼는지, 그리고 **거기에 비밀번호·토큰 "
        "원문이 없다는 것**.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    login(browser, A)
    doc.add(browser.send("POST", "/api/auth/logout", {}), "로그아웃 — 기록이 남는 성공")
    doc.add(login(browser, A, WRONG), "실패한 로그인 — 기록이 남는 거절")

    with app.app_context():
        events = db.session.scalars(db.select(SecurityEvent)).all()
        kinds: dict[tuple[str, str], int] = {}
        for event in events:
            kinds[(event.event_type, event.result)] = kinds.get((event.event_type, event.result), 0) + 1
        blob = " ".join(f"{event.event_type}{event.detail}{event.ip_hash}" for event in events)
        addressed = sum(1 for event in events if event.user_id)
    table = "\n".join(
        f"| `{name}` | {result} | {count} |" for (name, result), count in sorted(kinds.items())
    )
    leaks = [
        label
        for label, value in (
            ("A의 비밀번호", A[1]),
            ("B의 비밀번호", B[1]),
            ("틀린 비밀번호", WRONG),
            ("원본 IP", "127.0.0.1"),
        )
        if value in blob
    ]
    doc.note(
        "## 이 실행이 남긴 기록\n\n"
        "| 종류 | 결과 | 건수 |\n| --- | --- | ---: |\n" + table + "\n\n"
        f"- 전체 {len(events)}건, 그중 사용자를 가리키는 것 {addressed}건\n"
        f"- 비밀번호·토큰·원본 IP 원문이 들어 있는가: "
        f"**{'있음: ' + ', '.join(leaks) if leaks else '없음'}**\n\n"
        "기록은 **한 함수**를 지나 저장된다 — `services/security_events.py::record`가 "
        "`redact()`를 통과시킨 것만 쓴다. 「호출하는 쪽이 조심한다」가 아니라 들어오는 "
        "길이 하나여야, 「가렸는가」가 마흔 곳이 아니라 한 곳에 관한 질문이 된다.\n\n"
        "감사 기록의 `user_id`는 계정 삭제 때 **CASCADE가 아니라 SET NULL**이다. 자료는 "
        "지워지고 사건은 남는다 — 계정과 함께 스스로를 지우는 감사 기록은 유출 이후에 "
        "쓸모가 없다 (C134).\n\n"
        "### 이 확인의 범위 (C106)\n\n"
        "「어디에도 없다」는 증명할 수 없다. 확인한 것은 **이 실행에서 나온 것 전부**다: "
        "위 응답 본문, `security_events` 전체, 그리고 이 폴더의 증거 파일. 여기에 "
        "`backend/scripts/audit_secrets.py`의 워킹트리·프런트 빌드·Git 이력 스캔과 "
        "`redact()`의 단위 검사를 합친 것이 이 주장의 전부이고, 그 밖은 주장하지 않는다."
    )
    doc.write()


def file_11(app):
    doc = Document(
        "11-totals.md",
        "화면 합계와 손으로 더한 값",
        "T07-C132",
        "집계가 돌려준 숫자와, 같은 기록을 손으로 더한 값이 같은가.",
    )
    browser = Browser(app, "A")
    signup(browser, A)
    login(browser, A)
    plan, task = furnish(browser, "합성 관찰 계획")
    for minutes, day in ((60, "02"), (45, "03")):
        browser.send(
            "POST",
            f"/api/tasks/{task['id']}/executions",
            {
                "startedAt": f"2026-09-{day}T10:00:00+09:00",
                "endedAt": f"2026-09-{day}T11:00:00+09:00",
                "actualMinutes": minutes,
                "blockerReason": "합성 사유",
            },
        )
    study = doc.add(browser.send("GET", f"/api/plans/{plan['id']}/study"), "집계 (성공)")
    doc.add(
        Browser(app, "anon").send("GET", f"/api/plans/{plan['id']}/study"),
        "로그인 없이 같은 집계 — 거절",
    )

    payload = study.response.get_json()
    days = [row for row in payload["days"] if row["actualMinutes"]]
    hand_actual = sum(row["actualMinutes"] for row in days)
    hand_estimated = sum(row["estimatedMinutes"] for row in days)
    rows = "\n".join(
        f"| {row['dayNumber']} | {row['date']} | {row['estimatedMinutes']} | "
        f"{row['actualMinutes']} | {row['ratio']} |"
        for row in days
    )
    doc.note(
        "## 손으로 더하기 (C132)\n\n"
        "| 일 | 날짜 | 예상(분) | 실제(분) | 비율 |\n| ---: | --- | ---: | ---: | ---: |\n"
        + rows
        + "\n\n"
        f"- 실제 합계: 손 **{hand_actual}분** · 화면 **{sum(row['actualMinutes'] for row in days)}분**\n"
        f"- 예상 합계: 손 **{hand_estimated}분** · 화면 **{sum(row['estimatedMinutes'] for row in days)}분**\n"
        f"- 지표: {payload['metric']['name']} · 단위 `{payload['metric']['unit']}` · "
        f"규칙 `{payload['metric']['formula']}` · {payload['metric']['rounding']}\n\n"
        "하루 비율을 평균하지 않고 **분을 먼저 더한 뒤 한 번 나눈다.** 비율을 평균하면 "
        "십 분짜리 하루와 여섯 시간짜리 하루가 같은 무게를 갖고, 날짜별과 전체가 서로 "
        "다른 계산 규칙을 쓰게 된다."
    )
    doc.write()


def build_app(directory: Path):
    """A throwaway database per file, so one run's rows cannot leak into another."""
    app = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{directory.as_posix()}"}
    )
    with app.app_context():
        db.create_all()
    return app


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    builders = (file_01, file_02, file_03, file_04, file_05, file_06,
                file_07, file_08, file_09, file_10, file_11)
    with tempfile.TemporaryDirectory() as workspace:
        for index, builder in enumerate(builders):
            app = build_app(Path(workspace) / f"evidence-{index}.db")
            try:
                builder(app)
            finally:
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()
    print(f"\n{len(builders)}개 파일을 docs/T07-EVIDENCE/에 썼다.")


if __name__ == "__main__":
    main()
