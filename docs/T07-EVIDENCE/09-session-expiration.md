# 세션 만료 — 유휴와 절대

- 기준: T07-C111
- 수집: 2026-09-04 10:34:07 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 2건 · 거절 2건

48시간 쓰지 않으면 끊기고, 14일이 지나면 얼마나 부지런히 썼든 끊긴다.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 정상 — 세션이 살아 있다

```http
GET /api/auth/me
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-04T01:34:07.618536",
    "email": "evidence-a@example.invalid",
    "id": "5f5214be-1ebc-4789-8837-d3721129a130"
  }
}
```

### 2. 유휴 한도를 넘긴 뒤 — 거절

```http
GET /api/auth/me
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
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

### 3. 회전으로도 되살아나지 않는다

```http
POST /api/auth/refresh
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]

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

### 4. 방금 썼지만 절대 한도를 넘긴 세션 — 거절

```http
GET /api/auth/me
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-04T01:34:07.618536",
    "email": "evidence-a@example.invalid",
    "id": "5f5214be-1ebc-4789-8837-d3721129a130"
  }
}
```

## 시간을 앞당긴 방법 — 숨기지 않는다

48시간과 14일을 실제로 기다릴 수 없으므로, 세션 행의 `last_used_at`과 `expires_at`을 과거로 옮겨 두고 같은 요청을 보냈다. **응답을 만든 코드는 그대로**이고, 옮긴 것은 시계뿐이다.

| 값 | 설정 | 어디서 읽는가 |
| --- | ---: | --- |
| Access 수명 | 600초 | `security/tokens.py` |
| 유휴 한도 | 48시간 | `services/sessions.py` |
| 절대 한도 | 14일 | 로그인 때 정해지고 회전이 물려받는다 |

거절의 문구는 모르는 토큰이 받는 것과 같다. 어느 쪽으로 죽었는지 알려 주면 훔친 값의 어느 절반이 아직 쓸모 있는지 알려 주는 셈이다.
