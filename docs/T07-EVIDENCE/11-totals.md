# 화면 합계와 손으로 더한 값

- 기준: T07-C132
- 수집: 2026-09-05 19:54:27 +0900 · `backend/scripts/collect_auth_evidence.py` 실행 결과
- 성공 1건 · 거절 1건

집계가 돌려준 숫자와, 같은 기록을 손으로 더한 값이 같은가.

> 이 파일은 손으로 쓰지 않는다. 아래 요청·응답은 모두 그 실행에서 나온 것이고,
> 값은 전부 `app/security/redact.py` 한 곳을 지난다.

### 1. 집계 (성공)

```http
GET /api/plans/9c78d317-84e6-49ad-b2d4-cce5b261a8ce/study
Cookie: access=[redacted], csrf=[redacted]
```

```http
200 OK
Set-Cookie: (없음)

{
  "days": [
    {
      "actualMinutes": 90,
      "date": "2026-09-01",
      "dayNumber": 1,
      "estimatedMinutes": 0,
      "executionCount": 1,
      "ratio": null
    },
    {
      "actualMinutes": 60,
      "date": "2026-09-02",
      "dayNumber": 2,
      "estimatedMinutes": 120,
      "executionCount": 1,
      "ratio": 0.5
    },
    {
      "actualMinutes": 45,
      "date": "2026-09-03",
      "dayNumber": 3,
      "estimatedMinutes": 0,
      "executionCount": 1,
      "ratio": null
    },
    {
      "actualMinutes": 0,
      "date": "2026-09-04",
      "dayNumber": 4,
      "estimatedMinutes": 0,
      "executionCount": 0,
      "ratio": null
    },
    {
      "actualMinutes": 0,
      "date": "2026-09-05",
      "dayNumber": 5,
      "estimatedMinutes": 0,
      "executionCount": 0,
      "ratio": null
    },
    {
      "actualMinutes": 0,
      "date": "2026-09-06",
      "dayNumber": 6,
      "estimatedMinutes": 0,
      "executionCount": 0,
      "ratio": null
    },
    {
      "actualMinutes": 0,
      "date": "2026-09-07",
      "dayNumber": 7,
      "estimatedMinutes": 0,
      "executionCount": 0,
      "ratio": null
    }
  ],
  "endDate": "2026-09-07",
  "executions": [
    {
      "actualMinutes": 90,
      "blockerReason": "합성 사유",
      "createdAt": "2026-09-05T10:54:27.031592+00:00",
      "dayNumber": 1,
      "durationUnit": "minutes",
      "endedAt": "2026-09-01T05:30:00+00:00",
      "id": "1ce5f01f-52e7-46d7-b341-3bdca0f5fca8",
      "startedAt": "2026-09-01T04:00:00+00:00",
      "taskContent": "합성 할 일",
      "taskId": "e9ca9a79-
```

### 2. 로그인 없이 같은 집계 — 거절

```http
GET /api/plans/9c78d317-84e6-49ad-b2d4-cce5b261a8ce/study
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

## 손으로 더하기 (C132)

| 일 | 날짜 | 예상(분) | 실제(분) | 비율 |
| ---: | --- | ---: | ---: | ---: |
| 1 | 2026-09-01 | 0 | 90 | None |
| 2 | 2026-09-02 | 120 | 60 | 0.5 |
| 3 | 2026-09-03 | 0 | 45 | None |

- 실제 합계: 손 **195분** · 화면 **195분**
- 예상 합계: 손 **120분** · 화면 **120분**
- 지표: 하루 계획 대비 실제 비율 · 단위 `배` · 규칙 `실제분 ÷ 예상분` · 소수 둘째 자리 반올림

하루 비율을 평균하지 않고 **분을 먼저 더한 뒤 한 번 나눈다.** 비율을 평균하면 십 분짜리 하루와 여섯 시간짜리 하루가 같은 무게를 갖고, 날짜별과 전체가 서로 다른 계산 규칙을 쓰게 된다.
