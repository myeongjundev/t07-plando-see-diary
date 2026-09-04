# 가입 · 로그인 · 로그아웃

- 기준: T07-C94 · C95 · C96 · C98 · C99
- 수집: 2026-09-04 10:34:05 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 3건 · 거절 3건

계정을 만들고, 그 계정으로 들어가고, 나온다. 그리고 같은 주소로 두 번 가입되지 않는 것과, 로그인이 실패하는 두 경우가 **같은 문장·같은 상태**로 답하는 것.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 가입 (C94)

```http
POST /api/auth/signup
Cookie: (없음)

{
  "email": "evidence-a@example.invalid",
  "password": "[redacted]"
}
```

```http
201 CREATED
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-04T01:34:05.062506",
    "email": "evidence-a@example.invalid",
    "id": "54e2f324-dd81-4608-9462-9d613fe1c089"
  }
}
```

### 2. 같은 주소로 다시 가입 — 거절 (C98)

```http
POST /api/auth/signup
Cookie: (없음)

{
  "email": "evidence-a@example.invalid",
  "password": "[redacted]"
}
```

```http
409 CONFLICT
Set-Cookie: (없음)

{
  "error": {
    "details": {
      "email": "이미 가입된 이메일입니다."
    },
    "message": "계정을 만들 수 없습니다."
  }
}
```

### 3. 로그인 (C95)

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
    "createdAt": "2026-09-04T01:34:05.062506",
    "email": "evidence-a@example.invalid",
    "id": "54e2f324-dd81-4608-9462-9d613fe1c089"
  }
}
```

### 4. 로그아웃 (C96)

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

### 5. 비밀번호만 틀림 (C99)

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

### 6. 없는 계정 (C99)

```http
POST /api/auth/login
Cookie: (없음)

{
  "email": "nobody@example.invalid",
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

**두 거절의 본문이 글자 단위로 같은가: 같다** · 상태 401 / 401

문구가 같아도 응답이 열 배 빨리 오면 같은 것을 말한 것이 아니다. 없는 계정에도 실제 Argon2 검증을 한 번 돌리는 이유가 그것이고, 그 사실은 `app/security/passwords.py::dummy_verify`에 있다.
