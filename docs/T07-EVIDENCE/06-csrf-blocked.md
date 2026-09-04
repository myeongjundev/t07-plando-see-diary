# 교차 사이트 요청 막기

- 기준: 설명서 ⑥ · 설계 5절
- 수집: 2026-09-04 10:34:06 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 1건 · 거절 4건

같은 로그인 상태에서 **정상 · 헤더 없음 · 헤더 불일치 · JSON 아님 · 교차 출처** 다섯 가지. 달라진 것은 요청의 모양뿐이다.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 정상 — 쿠키와 헤더가 맞는다

```http
POST /api/plans
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]

{
  "title": "합성 계획",
  "startDate": "2026-09-01",
  "endDate": "2026-09-07",
  "priority": "high",
  "successCriterion": "합성 성공 기준",
  "estimatedMinutes": 600
}
```

```http
201 CREATED
Set-Cookie: (없음)

{
  "plan": {
    "carriedImprovement": null,
    "createdAt": "2026-09-04T01:34:06.438257+00:00",
    "durationUnit": "minutes",
    "endDate": "2026-09-07",
    "estimatedMinutes": 600,
    "id": "fd258268-1211-459e-8e58-dfc52935aa57",
    "priority": "high",
    "startDate": "2026-09-01",
    "successCriterion": "합성 성공 기준",
    "title": "합성 계획",
    "updatedAt": "2026-09-04T01:34:06.438258+00:00"
  }
}
```

### 2. 헤더 없음 — 거절

```http
POST /api/plans
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]

{
  "title": "합성 계획",
  "startDate": "2026-09-01",
  "endDate": "2026-09-07",
  "priority": "high",
  "successCriterion": "합성 성공 기준",
  "estimatedMinutes": 600
}
```

```http
403 FORBIDDEN
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "요청을 확인할 수 없습니다."
  }
}
```

### 3. 헤더 불일치 — 거절

```http
POST /api/plans
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
X-CSRF-Token: [redacted]

{
  "title": "합성 계획",
  "startDate": "2026-09-01",
  "endDate": "2026-09-07",
  "priority": "high",
  "successCriterion": "합성 성공 기준",
  "estimatedMinutes": 600
}
```

```http
403 FORBIDDEN
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "요청을 확인할 수 없습니다."
  }
}
```

### 4. JSON 아님 — 거절 (415)

```http
POST /api/auth/login
Cookie: (없음)
Content-Type: application/x-www-form-urlencoded
```

```http
415 UNSUPPORTED MEDIA TYPE
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "요청 형식이 올바르지 않습니다."
  }
}
```

### 5. 교차 출처 — 거절

```http
POST /api/plans
Cookie: access=[redacted], refresh=[redacted], csrf=[redacted]
Origin: https://attacker.example
X-CSRF-Token: [redacted]

{
  "title": "합성 계획",
  "startDate": "2026-09-01",
  "endDate": "2026-09-07",
  "priority": "high",
  "successCriterion": "합성 성공 기준",
  "estimatedMinutes": 600
}
```

```http
403 FORBIDDEN
Set-Cookie: (없음)

{
  "error": {
    "details": {},
    "message": "요청을 확인할 수 없습니다."
  }
}
```

세 겹이라 하나가 무너져도 나머지가 남는다: SameSite · JSON과 Origin · `__Host-` 이중 제출. 브라우저가 스크립트 없이 보낼 수 있는 폼 POST는 `application/json`을 만들 수 없고, 그걸 만들려면 사전 요청이 필요한데 CORS 헤더를 하나도 내주지 않는다 (설계 5절).
