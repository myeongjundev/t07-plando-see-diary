# 무차별 대입 잠금

- 기준: 설명서 ⑤ · 설계 6절
- 수집: 2026-09-04 10:34:07 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 2건 · 거절 8건

같은 (계정, 주소)로 다섯 번 틀리면 잠긴다. **없는 계정도 똑같이 잠긴다** — 안 그러면 「잠기지 않는다」가 곧 「그런 계정 없다」가 된다.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 정상 로그인 — 잠금 전

```http
POST /api/auth/login
Cookie: (없음)

{
  "email": "evidence-a@example.invalid",
  "password": "[redacted]"
}
```

```http
200 OK
Set-Cookie: __Host-pds_access=[redacted], __Secure-pds_refresh=[redacted], __Host-pds_csrf=[redacted]

{
  "user": {
    "createdAt": "2026-09-04T01:34:06.604317",
    "email": "evidence-a@example.invalid",
    "id": "845e2206-d854-44bb-b1cc-9ac5836487b6"
  }
}
```

### 2. 틀린 비밀번호 1회

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

### 3. 틀린 비밀번호 2회

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

### 4. 틀린 비밀번호 3회

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

### 5. 틀린 비밀번호 4회

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

### 6. 틀린 비밀번호 5회

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

### 7. 여섯 번째 — 429

```http
POST /api/auth/login
Cookie: (없음)

{
  "email": "evidence-a@example.invalid",
  "password": "[redacted]"
}
```

```http
429 TOO MANY REQUESTS
Set-Cookie: (없음)
Retry-After: 60

{
  "error": {
    "details": {},
    "message": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
  }
}
```

### 8. 맞는 비밀번호로도 — 여전히 429

```http
POST /api/auth/login
Cookie: (없음)

{
  "email": "evidence-a@example.invalid",
  "password": "[redacted]"
}
```

```http
429 TOO MANY REQUESTS
Set-Cookie: (없음)
Retry-After: 60

{
  "error": {
    "details": {},
    "message": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
  }
}
```

### 9. 없는 계정도 같은 횟수에 같은 429

```http
POST /api/auth/login
Cookie: (없음)

{
  "email": "nobody@example.invalid",
  "password": "[redacted]"
}
```

```http
429 TOO MANY REQUESTS
Set-Cookie: (없음)
Retry-After: 60

{
  "error": {
    "details": {},
    "message": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
  }
}
```

### 10. 첫 잠금이 지난 뒤 — 다시 들어온다

```http
POST /api/auth/login
Cookie: (없음)

{
  "email": "evidence-a@example.invalid",
  "password": "[redacted]"
}
```

```http
200 OK
Set-Cookie: __Host-pds_access=[redacted], __Secure-pds_refresh=[redacted], __Host-pds_csrf=[redacted]

{
  "user": {
    "createdAt": "2026-09-04T01:34:06.604317",
    "email": "evidence-a@example.invalid",
    "id": "845e2206-d854-44bb-b1cc-9ac5836487b6"
  }
}
```

- 창 15분 · 임계 5회(계정+주소) 또는 20회(주소)
- 첫 잠금 60초, 이후 실패마다 배증, 최대 15분
- 있는 계정과 없는 계정의 응답이 같은가: **같다** (429 / 429)
- 맞는 비밀번호로도 잠금을 넘지 못한다: 429

**잠금 중 요청은 실패 횟수에 넣지 않는다.** 넣으면 공격자가 요청만 계속 보내 피해자를 창 내내 붙들 수 있다. IP는 원문을 저장하지 않고 `HMAC-SHA-256(IP_HASH_SECRET, 주소)`로만 남는다.

여기서 정직하게 교환한 것 하나: 잠긴 정상 사용자에게 「잠겼습니다」라고 말하지 않는다. 그 안내가 곧 계정이 있다는 증거가 되기 때문이고, 존재를 감추는 쪽을 골랐다. 설명서 ⑥.
