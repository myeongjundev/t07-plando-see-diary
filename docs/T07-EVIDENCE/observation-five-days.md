# T07 5일 실제 관찰 — 배포본 응답

2026-09-11 KST. 고정한 관찰 계획
`8848a88f-3814-43dc-a454-f87007b61ba7`의 인증된
`GET /api/plans/8848a88f-3814-43dc-a454-f87007b61ba7/study` 응답이다.
운영 화면의 5일 표와 전체 JSON 내보내기에 저장된 원본 실행 기록을 대조했다.

```json
{
  "planId": "8848a88f-3814-43dc-a454-f87007b61ba7",
  "metric": {
    "key": "dailyPlannedVsActual",
    "name": "하루 계획 대비 실제 비율",
    "unit": "배",
    "formula": "실제분 ÷ 예상분",
    "rounding": "소수 둘째 자리 반올림",
    "timezone": "Asia/Seoul"
  },
  "startDate": "2026-09-07",
  "endDate": "2026-09-11",
  "days": [
    {
      "dayNumber": 1,
      "date": "2026-09-07",
      "estimatedMinutes": 30,
      "actualMinutes": 30,
      "executionCount": 1,
      "ratio": 1.0
    },
    {
      "dayNumber": 2,
      "date": "2026-09-08",
      "estimatedMinutes": 30,
      "actualMinutes": 8,
      "executionCount": 1,
      "ratio": 0.27
    },
    {
      "dayNumber": 3,
      "date": "2026-09-09",
      "estimatedMinutes": 10,
      "actualMinutes": 4,
      "executionCount": 1,
      "ratio": 0.4
    },
    {
      "dayNumber": 4,
      "date": "2026-09-10",
      "estimatedMinutes": 10,
      "actualMinutes": 4,
      "executionCount": 1,
      "ratio": 0.4
    },
    {
      "dayNumber": 5,
      "date": "2026-09-11",
      "estimatedMinutes": 10,
      "actualMinutes": 4,
      "executionCount": 1,
      "ratio": 0.4
    }
  ],
  "executions": [
    {
      "id": "062270eb-03ea-4f63-8135-f4f5a69f6980",
      "taskId": "5282da51-e13e-463a-b276-3c861e95f574",
      "startedAt": "2026-09-06T15:00:00+00:00",
      "endedAt": "2026-09-06T15:30:00+00:00",
      "actualMinutes": 30,
      "durationUnit": "minutes",
      "blockerReason": "",
      "createdAt": "2026-09-06T16:13:39.700792+00:00",
      "taskContent": "README 최종 검토 제출 준비",
      "dayNumber": 1
    },
    {
      "id": "c26ca959-0b3c-488b-958b-fa67182ea8d3",
      "taskId": "80cc86dd-4b4f-43ef-b8ce-975a199e3cdf",
      "startedAt": "2026-09-07T17:18:00+00:00",
      "endedAt": "2026-09-07T17:26:00+00:00",
      "actualMinutes": 8,
      "durationUnit": "minutes",
      "blockerReason": "",
      "createdAt": "2026-09-07T17:26:47.968858+00:00",
      "taskContent": "설정 화면 시각 검토 및 마감 준비",
      "dayNumber": 2
    },
    {
      "id": "fd95c386-f2de-4e59-ab18-b69b4a6c86b3",
      "taskId": "483dd72d-3325-480f-8a57-09b0ebb29a83",
      "startedAt": "2026-09-08T15:05:00+00:00",
      "endedAt": "2026-09-08T15:09:00+00:00",
      "actualMinutes": 4,
      "durationUnit": "minutes",
      "blockerReason": "",
      "createdAt": "2026-09-08T15:10:47.642265+00:00",
      "taskContent": "T07 3일차 상태 확인 및 기록 정리",
      "dayNumber": 3
    },
    {
      "id": "ef80f838-777b-4b16-82c2-dfa6565ad8e7",
      "taskId": "9f20751f-9939-4d55-b996-26b7d141161b",
      "startedAt": "2026-09-09T16:12:00+00:00",
      "endedAt": "2026-09-09T16:16:00+00:00",
      "actualMinutes": 4,
      "durationUnit": "minutes",
      "blockerReason": "",
      "createdAt": "2026-09-09T16:20:47.623773+00:00",
      "taskContent": "T07 4일차 운영 상태 확인 및 기록",
      "dayNumber": 4
    },
    {
      "id": "36ed83e8-aa2b-437b-a5fa-eb1b0937402f",
      "taskId": "f79a4e17-5127-4cf4-9c6b-d77e8b0903ff",
      "startedAt": "2026-09-10T15:10:00+00:00",
      "endedAt": "2026-09-10T15:14:00+00:00",
      "actualMinutes": 4,
      "durationUnit": "minutes",
      "blockerReason": "",
      "createdAt": "2026-09-10T15:14:42.905934+00:00",
      "taskContent": "T07 5일차 최종 검증 및 제출 준비",
      "dayNumber": 5
    }
  ]
}
```

## 손계산과 화면 대조

| 구간 | 손계산 | 배포 화면 |
| --- | --- | --- |
| 변경 전 1–2일차 | `(30 + 8) ÷ (30 + 30) = 38 ÷ 60 = 0.63배` | `0.63배 · 예상 60분 · 실제 38분 · 2일` |
| 변경 후 3–5일차 | `(4 + 4 + 4) ÷ (10 + 10 + 10) = 12 ÷ 30 = 0.40배` | `0.40배 · 예상 30분 · 실제 12분 · 3일` |
| 전체 5일 | `(30 + 8 + 4 + 4 + 4) ÷ (30 + 30 + 10 + 10 + 10) = 50 ÷ 90 = 0.56배` | 할 일 예상 `90분` · 실제 `50분` |

5개 날짜 모두 예상분·실제분·실행 기록이 있어 결측·중복 제외가 없다. 규칙 변경은
2일차 실행 종료 뒤인 2026-09-08 02:27 KST에 한 번 저장됐고, 3일차 실행은 그 뒤인
2026-09-09 00:05 KST에 시작했다.
