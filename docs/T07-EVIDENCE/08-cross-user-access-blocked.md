# 남의 자료가 안 열리는 것

- 기준: T07-C116 ~ C126
- 수집: 2026-09-05 19:54:24 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 3건 · 거절 8건

계정 두 개에 각각 자료를 넣고, **양방향으로** 읽기·수정·삭제를 시도한다. 주소·헤더·본문에 남의 ID를 적어 보낸 것과, 로그인하지 않은 요청도 함께.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. A가 자기 계획을 읽는다 (C116)

```http
GET /api/plans/9bbd2e56-e2ea-4592-8f28-a40e496531f9
Cookie: access=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "plan": {
    "carriedImprovement": null,
    "createdAt": "2026-09-05T10:54:24.670398+00:00",
    "durationUnit": "minutes",
    "endDate": "2026-09-07",
    "estimatedMinutes": 600,
    "id": "9bbd2e56-e2ea-4592-8f28-a40e496531f9",
    "priority": "high",
    "startDate": "2026-09-01",
    "successCriterion": "합성 성공 기준",
    "title": "앨리스의 합성 계획",
    "updatedAt": "2026-09-05T10:54:24.670398+00:00"
  }
}
```

### 2. A → B 읽기 (C117)

```http
GET /api/plans/eefd09ba-eaf6-4265-aaf9-e6ac10585d45
Cookie: access=[redacted], csrf=[redacted]
```

```http
404 NOT FOUND
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "계획을 찾을 수 없습니다."
  }
}
```

### 3. A → B 수정 (C118)

```http
PATCH /api/plans/eefd09ba-eaf6-4265-aaf9-e6ac10585d45
Cookie: access=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]
Content-Type: application/json

{
  "estimatedMinutes": 1
}
```

```http
404 NOT FOUND
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "계획을 찾을 수 없습니다."
  }
}
```

### 4. A → B 삭제 (C119)

```http
DELETE /api/tasks/4c1febdf-3234-4238-a296-21af2014a8a3
Cookie: access=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]
Content-Type: application/json

{}
```

```http
404 NOT FOUND
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "할 일을 찾을 수 없습니다."
  }
}
```

### 5. B → A 읽기 (C120)

```http
GET /api/plans/9bbd2e56-e2ea-4592-8f28-a40e496531f9
Cookie: access=[redacted], csrf=[redacted]
```

```http
404 NOT FOUND
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "계획을 찾을 수 없습니다."
  }
}
```

### 6. B → A 수정 (C120)

```http
PATCH /api/plans/9bbd2e56-e2ea-4592-8f28-a40e496531f9
Cookie: access=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]
Content-Type: application/json

{
  "estimatedMinutes": 1
}
```

```http
404 NOT FOUND
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "계획을 찾을 수 없습니다."
  }
}
```

### 7. B → A 삭제 (C120)

```http
DELETE /api/tasks/da8e7a35-47c0-4ca6-905b-5b7bc1c49a22
Cookie: access=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]
Content-Type: application/json

{}
```

```http
404 NOT FOUND
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "할 일을 찾을 수 없습니다."
  }
}
```

### 8. 주소·헤더에 남을 적어 보냄 — 그래도 내 것만 (C123)

```http
GET /api/plans?userId=465184ac-d035-4aad-8390-a2a9595ff8bb
Cookie: access=[redacted], csrf=[redacted]
X-User-Id: 465184ac-d035-4aad-8390-a2a9595ff8bb
```

```http
200 OK
Set-Cookie: (없음)

{
  "plans": [
    {
      "carriedImprovement": null,
      "createdAt": "2026-09-05T10:54:24.670398+00:00",
      "durationUnit": "minutes",
      "endDate": "2026-09-07",
      "estimatedMinutes": 600,
      "id": "9bbd2e56-e2ea-4592-8f28-a40e496531f9",
      "priority": "high",
      "startDate": "2026-09-01",
      "successCriterion": "합성 성공 기준",
      "title": "앨리스의 합성 계획",
      "updatedAt": "2026-09-05T10:54:24.670398+00:00"
    }
  ]
}
```

### 9. 본문에 B의 계정 ID를 넣어 생성 — 허용하지 않는 필드라 거절 (C123)

```http
POST /api/plans
Cookie: access=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]
Content-Type: application/json

{
  "title": "합성 계획",
  "startDate": "2026-09-01",
  "endDate": "2026-09-07",
  "priority": "high",
  "successCriterion": "합성 성공 기준",
  "estimatedMinutes": 600,
  "userId": "465184ac-d035-4aad-8390-a2a9595ff8bb"
}
```

```http
400 BAD REQUEST
Set-Cookie: (없음)

{
  "error": {
    "details": {
      "body": "알 수 없는 항목: userId"
    },
    "message": "계획을 저장할 수 없습니다."
  }
}
```

### 10. 로그인하지 않고 자료 요청 (C124)

```http
GET /api/plans
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

### 11. 목록에 남의 것이 없다 (C125)

```http
GET /api/plans
Cookie: access=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "plans": [
    {
      "carriedImprovement": null,
      "createdAt": "2026-09-05T10:54:24.670398+00:00",
      "durationUnit": "minutes",
      "endDate": "2026-09-07",
      "estimatedMinutes": 600,
      "id": "9bbd2e56-e2ea-4592-8f28-a40e496531f9",
      "priority": "high",
      "startDate": "2026-09-01",
      "successCriterion": "합성 성공 기준",
      "title": "앨리스의 합성 계획",
      "updatedAt": "2026-09-05T10:54:24.670398+00:00"
    }
  ]
}
```

## 거절 앞뒤 건수 (C122)

| 계정 | 계획 전 | 계획 후 | 할 일 전 | 할 일 후 |
| --- | ---: | ---: | ---: | ---: |
| A | 1 | 1 | 1 | 1 |
| B | 1 | 1 | 1 | 1 |

- A의 목록에 B의 계획 ID가 들어 있는가: **없다** (C125)
- 위조한 요청이 돌려준 계획 수: 1건 — 내 것뿐 (C123)

타인 자료 읽기·수정·삭제 거절은 **404**다. 위조한 생성 본문은 400, 무인증은 401이다. 403은 「있지만 당신 것이 아니다」를 말해 주고, 그건 남의 ID가 실재하는지 확인해 주는 통로가 된다 (C121). 거절을 만드는 곳은 세 파일뿐이다 — `guards.py` · `ownership.py` · `csrf.py` (C126).
