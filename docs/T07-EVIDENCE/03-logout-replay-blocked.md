# 로그아웃 전후, 같은 요청

- 기준: T07-C108 · C109 · C110 · C114
- 수집: 2026-09-04 10:40:09 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 2건 · 거절 1건

**같은 주소·같은 방식**의 요청을 로그아웃 앞뒤로 한 번씩. 달라진 것은 로그아웃 여부뿐이다.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 로그아웃 전 — `GET /api/auth/me`

```http
GET /api/auth/me
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-04T01:40:09.473357",
    "email": "evidence-a@example.invalid",
    "id": "1e4cfd7f-9464-4b2d-af5f-657f8ba12b76"
  }
}
```

### 2. 로그아웃

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

### 3. 로그아웃 후 — **같은 요청**

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

두 요청의 메서드와 주소가 같다: `GET /api/auth/me`. 첫 번째는 200, 세 번째는 401. 중간에 일어난 일은 로그아웃뿐이다 (C109 · C110).

Access 토큰은 그 사이에 만료하지 않았다 — 서명도 유효하고 수명(600초)도 남아 있다. 그래도 통하지 않는 것은 가드가 토큰만 보지 않고 세션 행을 읽기 때문이고, 그것이 C114가 요구하는 「이전에 발급한 값이 더는 통하지 않는다」다 (설계 1절).
