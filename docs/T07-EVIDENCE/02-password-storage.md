# 비밀번호를 어떻게 맡아 두는가

- 기준: T07-C101 ~ C107
- 수집: 2026-09-04 10:40:09 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 2건 · 거절 1건

저장된 값의 모양과, **같은 비밀번호로 만든 두 계정의 저장 값이 서로 다른 것**. 뒤쪽은 인증 서비스를 골랐다면 만들 수 없는 장면이다.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 같은 비밀번호로 계정 1

```http
POST /api/auth/signup
Cookie: (없음)

{
  "email": "same-1@example.invalid",
  "password": "[redacted]"
}
```

```http
201 CREATED
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-04T01:40:09.247508",
    "email": "same-1@example.invalid",
    "id": "450894d3-31d8-4a4d-9694-0320f5d49c34"
  }
}
```

### 2. 같은 비밀번호로 계정 2

```http
POST /api/auth/signup
Cookie: (없음)

{
  "email": "same-2@example.invalid",
  "password": "[redacted]"
}
```

```http
201 CREATED
Set-Cookie: (없음)

{
  "user": {
    "createdAt": "2026-09-04T01:40:09.283424",
    "email": "same-2@example.invalid",
    "id": "501e4524-48fc-4d09-9d00-b929ccc224f2"
  }
}
```

### 3. 그 주소로 다시 가입 — 거절

```http
POST /api/auth/signup
Cookie: (없음)

{
  "email": "same-1@example.invalid",
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

## 저장된 모습 (C103)

| 칸 | 값 |
| --- | --- |
| 알고리즘 | `argon2id` |
| 버전 | `v=19` |
| 매개변수 | `m=19456,t=2,p=1` |
| 소금 | (가림 — 값 안에 함께 들어 있다) |
| 해시 | (가림) |

- 전체 길이 97자
- **입력한 글자가 그대로 보이는가: 아니오.** 확인은 저장 값 안에서 원문을 찾아보는 것으로 했고, 결과는 **찾지 못함**이다. 그 원문을 여기 적지는 않는다 — 적는 순간 이 파일이 C105를 어긴다.
- 같은 비밀번호로 만든 두 계정의 저장 값이 서로 다른가 (C104): **다르다**
- 매개변수: `{"time_cost": 2, "memory_cost": 19456, "parallelism": 1}` — 소금과 매개변수가 값 안에 들어 있으므로 따로 관리하는 열이 없다

해시 원문은 싣지 않는다. 되돌릴 수 없다는 것과 오프라인 추측을 도와도 된다는 것은 다른 이야기다 (C131).
