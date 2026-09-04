# 남은 기록과, 거기 없는 것

- 기준: T07-C115 · C131 · 설계 7절
- 수집: 2026-09-04 10:34:08 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 1건 · 거절 1건

위의 모든 실행이 감사 기록에 무엇을 남겼는지, 그리고 **거기에 비밀번호·토큰 원문이 없다는 것**.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 로그아웃 — 기록이 남는 성공

```http
POST /api/auth/logout
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]

{}
```

```http
200 OK
Set-Cookie: __Host-pds_access=[redacted], __Secure-pds_refresh=[redacted], __Host-pds_csrf=[redacted]

{
  "ok": true
}
```

### 2. 실패한 로그인 — 기록이 남는 거절

```http
POST /api/auth/login
Cookie: (없음)

{
  "email": "evidence-a@example.invalid",
  "password": "[redacted]"
}
```

```http
401 UNAUTHORIZED
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "이메일 또는 비밀번호가 올바르지 않습니다."
  }
}
```

## 이 실행이 남긴 기록

| 종류 | 결과 | 건수 |
| --- | --- | ---: |
| `LOGIN_FAILURE` | failure | 1 |
| `LOGIN_SUCCESS` | success | 1 |
| `LOGOUT` | success | 1 |
| `SIGNUP_SUCCESS` | success | 1 |

- 전체 4건, 그중 사용자를 가리키는 것 3건
- 비밀번호·토큰·원본 IP 원문이 들어 있는가: **없음**

기록은 **한 함수**를 지나 저장된다 — `services/security_events.py::record`가 `redact()`를 통과시킨 것만 쓴다. 「호출하는 쪽이 조심한다」가 아니라 들어오는 길이 하나여야, 「가렸는가」가 마흔 곳이 아니라 한 곳에 관한 질문이 된다.

감사 기록의 `user_id`는 계정 삭제 때 **CASCADE가 아니라 SET NULL**이다. 자료는 지워지고 사건은 남는다 — 계정과 함께 스스로를 지우는 감사 기록은 유출 이후에 쓸모가 없다 (C134).

### 이 확인의 범위 (C106)

「어디에도 없다」는 증명할 수 없다. 확인한 것은 **이 실행에서 나온 것 전부**다: 위 응답 본문, `security_events` 전체, 그리고 이 폴더의 증거 파일. 여기에 `backend/scripts/audit_secrets.py`의 워킹트리·프런트 빌드·Git 이력 스캔과 `redact()`의 단위 검사를 합친 것이 이 주장의 전부이고, 그 밖은 주장하지 않는다.
