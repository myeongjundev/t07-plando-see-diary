# Refresh 회전

- 기준: T07-C111
- 수집: 2026-09-05 19:54:20 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 2건 · 거절 1건

A를 써서 B를 받고, 그 뒤 A는 죽는다. 한 번 쓴 값이 계속 통하면 훔친 값도 계속 통한다.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. A를 써서 B를 받는다

```http
POST /api/auth/refresh
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]
Content-Type: application/json

{}
```

```http
200 OK
Set-Cookie: __Host-pds_access=[redacted], __Secure-pds_refresh=[redacted]

{
  "ok": true
}
```

### 2. 새 Access로 요청 — 통한다

```http
GET /api/auth/me
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-05T10:54:20.806311",
    "email": "evidence-a@example.invalid",
    "id": "35f12ea6-7b71-4062-a635-fffe45451777"
  }
}
```

### 3. 쓴 A를 다시 — 거절

```http
POST /api/auth/refresh
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
Content-Type: application/json

{}
```

```http
401 UNAUTHORIZED
Set-Cookie: __Host-pds_access=[redacted], __Secure-pds_refresh=[redacted], __Host-pds_csrf=[redacted]

{
  "error": {
    "details": {},
    "message": "로그인이 필요합니다."
  }
}
```

- 쿠키 값이 바뀌었는가: **예** (두 값 모두 여기 싣지 않는다)

| # | 계열 | 상태 |
| ---: | --- | --- |
| 1 | 3f6c9364… | rotated |
| 2 | 3f6c9364… | reuse |

회전은 로그인 하나를 이어 가는 것이라 **계열이 같다.** 절대 만료도 물려받는다 — 회전이 늘릴 수 있는 한도는 절대 한도가 아니다 (C111).
