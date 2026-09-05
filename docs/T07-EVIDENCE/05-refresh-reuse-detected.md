# Refresh 재사용 탐지

- 기준: 설명서 ⑤ · 설계 4절
- 수집: 2026-09-05 19:54:21 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 2건 · 거절 2건

한 번 쓴 Refresh가 다시 오면 그 값은 그 사이에 **복제됐다는 뜻**이다. 누가 진짜인지 알 수 없으므로 그 로그인에서 뻗어 나온 계열을 통째로 끊는다.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 정상 회전

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

### 2. 회전 직후 — 통한다

```http
GET /api/auth/me
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-05T10:54:21.309279",
    "email": "evidence-a@example.invalid",
    "id": "1893ddd2-bfea-451b-9bba-b50a06cbe094"
  }
}
```

### 3. 쓴 값을 재생 — 거절

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

### 4. 재생 이후 — 계열이 끊겨 통하지 않는다

```http
GET /api/auth/me
Cookie: (없음)
```

```http
401 UNAUTHORIZED
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "로그인이 필요합니다."
  }
}
```

- `REFRESH_TOKEN_REUSE_DETECTED` 기록: **1건**
- 계열의 폐기 사유: ['reuse', 'rotated']

정상 사용자도 다시 로그인해야 한다. 그 대가를 알고 골랐다 — 도둑이 들고 간 후계 토큰을 살려 두는 것보다 낫다 (설계 11절).
