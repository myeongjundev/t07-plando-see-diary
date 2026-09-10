# -*- coding: utf-8 -*-
"""README 스크린샷용 합성 자료를 로컬 백엔드에 심는다.

    backend/.venv/Scripts/python.exe backend/local_server.py     # 다른 창에서
    SEED_PASSWORD=... python tools/seed_screenshot_fixture.py

자료가 없는 계정에 대고 돌린다. 이미 계획이 있으면 덧붙으므로, 집계를 맞추려면
새 계정을 쓰거나 기존 계획을 지운 뒤에 돌린다.

화면 스크린샷은 AGENTS.md 3번에 따라 합성 자료만 담아야 하므로 운영 DB가 아니라
로컬 SQLite를 대상으로 돌린다. 집계가 날짜에 따라 흔들리지 않도록 마감일을 «오늘»에서
상대적으로 잡는다 — 지연은 오늘보다 이른 미완료 할 일에서만 나온다(D-008, 서울 기준).

목표 집계: 할 일 5 · 완료 3 · 지연 1 · 막힘 2 · 예상 300분 · 실제 260분 · 차이 -40분

## T07 인증

T06에서는 API가 열려 있어 이 파일이 그냥 POST를 던지면 됐다. T07부터는 모든 쓰기가
세션과 CSRF를 요구하므로, 먼저 로그인해서 쿠키를 받고 그 뒤 모든 상태 변경 요청에
CSRF 값을 헤더로 옮겨 싣는다. 화면이 하는 일과 같다(`frontend/src/api/http.ts`).

Origin도 함께 보낸다. 서버가 상태 변경 요청의 Origin을 확인하므로, BASE와 다른 값을
보내면 403이 돌아온다. 기본 BASE는 `backend/local_server.py`가 여는 주소다.

비밀번호는 인자로 받지 않고 환경변수로만 받는다 — 명령줄은 셸 기록에 남는다.
"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = os.environ.get("SEED_BASE", "http://127.0.0.1:5099").rstrip("/")
EMAIL = os.environ.get("SEED_EMAIL", "preview@example.test")
PASSWORD = os.environ.get("SEED_PASSWORD")

# backend/app/auth/cookies.py와 같은 이름을 쓴다. 갈라지면 CSRF가 조용히 빠진 채
# 요청이 나가고 403만 보게 되므로, 바꿀 일이 있으면 양쪽을 같이 본다.
CSRF_COOKIE = "__Host-pds_csrf"
CSRF_HEADER = "X-CSRF-Token"

if not PASSWORD:
    raise SystemExit(
        "SEED_PASSWORD 환경변수가 필요합니다.\n"
        "  예: SEED_PASSWORD='...' python tools/seed_screenshot_fixture.py"
    )

class LocalhostSecurePolicy(http.cookiejar.DefaultCookiePolicy):
    """http://localhost에서도 Secure 쿠키를 돌려보낸다.

    서버는 TESTING이 아닌 한 항상 Secure를 붙인다(`backend/app/auth/cookies.py`).
    브라우저는 localhost에 한해 그 쿠키를 받아 주지만, 파이썬의 기본 정책은 http
    요청에 Secure 쿠키를 싣지 않는다 — 그대로 두면 로그인은 200으로 끝나고 그다음
    요청이 전부 401이 되어, 원인이 인증인지 CSRF인지 알기 어려운 실패가 된다.
    같은 함정이 Werkzeug 테스트 클라이언트에도 있고 그쪽 주석에도 적혀 있다.

    예외는 루프백에만 준다. 다른 호스트에서는 기본 정책 그대로다.
    """

    LOOPBACK = {"localhost", "127.0.0.1", "::1"}

    def return_ok_secure(self, cookie, request):
        if super().return_ok_secure(cookie, request):
            return True
        return urllib.parse.urlsplit(request.full_url).hostname in self.LOOPBACK


jar = http.cookiejar.CookieJar(policy=LocalhostSecurePolicy())
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def csrf_token():
    for cookie in jar:
        if cookie.name == CSRF_COOKIE:
            return cookie.value
    return None


def call(method, path, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "Origin": BASE}
    token = csrf_token()
    if token:
        headers[CSRF_HEADER] = token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with opener.open(req) as r:
            return json.load(r) if r.status != 204 else None
    except urllib.error.HTTPError as e:
        raise SystemExit("%s %s -> %s %s" % (method, path, e.code, e.read().decode("utf-8", "replace")))


print("로그인…", EMAIL, "@", BASE)
call("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})
if not csrf_token():
    raise SystemExit("로그인은 됐지만 CSRF 쿠키가 없습니다. BASE가 서버 주소와 같은지 확인하세요.")

existing = call("GET", "/api/plans")["plans"]
if existing:
    print("  주의: 이 계정에 이미 계획이 %d건 있습니다. 목표 집계와 어긋납니다." % len(existing),
          file=sys.stderr)

# 서울 기준 오늘. 로컬이 UTC+09가 아닐 수 있으므로 백엔드가 아니라 여기서 못박지 않고,
# 화면과 같은 규칙(자정 UTC 문자열 연산)으로 만든다.
TODAY = date.today()

d = lambda n: (TODAY + timedelta(days=n)).isoformat()
stamp = lambda n, h, m: "%sT%02d:%02d:00+09:00" % (d(n), h, m)

PLAN = {
    "title": "합성 · 이번 주 학습 계획",
    "startDate": d(-2), "endDate": d(4),
    "priority": "high",
    "successCriterion": "회고 한 줄을 다음 계획으로 넘긴다",
    "estimatedMinutes": 320,
    "carriedImprovement": None,
}

# (내용, 마감 오프셋, 우선순위, 태그, 예상분, 완료?, [(시작h, 분, 막힌 이유)])
TASKS = [
    ("SQLAlchemy 세션 수명 정리", -2, "high", ["backend", "study"], 60, True,
     [(9, 55, "")]),
    ("멱등 키 유니크 제약 실험", -1, "high", ["backend", "test"], 60, True,
     [(14, 70, "재현 조건을 못 잡아 30분 헤맴")]),
    ("집계 쿼리 조인 정리", 0, "medium", ["backend"], 60, True,
     [(10, 45, "")]),
    ("서울 시간대 경계 검토", -1, "medium", ["backend", "study"], 60, False,
     [(16, 50, "자정 경계 예제를 다시 만들어야 했다")]),
    ("회고 문장 다듬기", 2, "low", ["writing"], 60, False,
     [(20, 40, "")]),
]

print("계획 생성…")
plan = call("POST", "/api/plans", PLAN)["plan"]
pid = plan["id"]

for content, due, priority, tags, est, done, logs in TASKS:
    task = call("POST", "/api/plans/%s/tasks" % pid, {
        "content": content, "dueDate": d(due), "priority": priority,
        "tags": tags, "estimatedMinutes": est,
    })["task"]
    tid = task["id"]
    for hour, minutes, blocker in logs:
        call("POST", "/api/tasks/%s/executions" % tid, {
            "startedAt": stamp(due, hour, 0),
            "endedAt": stamp(due, hour + 1, 30),
            "actualMinutes": minutes,
            "blockerReason": blocker,
        })
    if done:
        call("POST", "/api/tasks/%s/complete" % tid, {"idempotencyKey": "seed-%s" % tid})
    print("  할 일:", content, "완료" if done else "진행 중")

# 다른 계획 몇 개 — 「다른 계획 N개」 목록이 비어 보이지 않도록.
for title, s, e, pr, crit, est in [
    ("합성 · 지난 주 학습 계획", -9, -3, "medium", "밀린 항목을 이번 주로 넘긴다", 240),
    ("합성 · 배포 점검", -1, 6, "low", "무중단으로 마이그레이션이 돈다", 120),
    ("합성 · 다음 주 준비", 5, 11, "high", "회고 개선점을 계획에 담는다", 300),
]:
    call("POST", "/api/plans", {
        "title": title, "startDate": d(s), "endDate": d(e), "priority": pr,
        "successCriterion": crit, "estimatedMinutes": est, "carriedImprovement": None,
    })
    print("  다른 계획:", title)

summary = call("GET", "/api/plans/%s/see" % pid)
keys = ["taskCount", "completedCount", "overdueCount", "blockedTaskCount",
        "estimatedMinutes", "actualMinutes", "varianceMinutes"]
values = [summary[k] for k in keys]
print("\n집계:", values)
print("계획 ID:", pid)

EXPECTED = [5, 3, 1, 2, 300, 260, -40]
if values != EXPECTED:
    print("\n경고: 목표 집계와 다릅니다. README의 alt 텍스트가 이 숫자를 주장합니다.",
          file=sys.stderr)
    print("  기대:", EXPECTED, file=sys.stderr)
    print("  실제:", values, file=sys.stderr)
    raise SystemExit(1)
print("목표 집계와 일치합니다.")
