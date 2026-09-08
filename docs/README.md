# 문서 안내

어느 문서가 유효한지 먼저 알려 주기 위한 색인입니다. 세 층으로 나눠 두었습니다.

## 지금 유효한 기준 (`docs/`)

읽고 따르면 되는 문서들입니다. 내용이 바뀌면 이 자리에서 고칩니다.

| 문서 | 내용 |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | 공식 과제에서 확정한 요구사항 |
| [T06-ACCEPTANCE-MATRIX.md](T06-ACCEPTANCE-MATRIX.md) | 고정 검사 44개. 통과시키려고 낮추지 않습니다 |
| [T06-VERIFICATION.md](T06-VERIFICATION.md) | 그 44개가 각각 어떻게 확인됐는지. 매트릭스에서 생성합니다 |
| [DECISIONS.md](DECISIONS.md) | 결정과 이유. 옛 결정은 고치지 않고 뒤집는 행을 더합니다 |
| [DESIGN.md](DESIGN.md) | 방향 선택 근거, 토큰, 건드리면 안 되는 화면 요소 |
| [FLASK-ARCHITECTURE.md](FLASK-ARCHITECTURE.md) | 서비스 경계, 표 구조, API 개요, 정렬·집계 규칙 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 로컬 실행과 검사 명령 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 로컬 운영 스택 (Docker Compose + 로컬 PostgreSQL) |
| [RENDER-NEON.md](RENDER-NEON.md) | 실제 배포 (Render Free + Neon) |
| [STATUS.md](STATUS.md) | 현재 상태, 근거, 남은 일 |
| [SUBMISSION.md](SUBMISSION.md) | 제출 주소와 제출문 |
| [T07-ACCEPTANCE-MATRIX.md](T07-ACCEPTANCE-MATRIX.md) | T07 고정 기준 68개와 검사 연결 |
| [T07-STUDY-PROTOCOL.md](T07-STUDY-PROTOCOL.md) | 2026-09-07~11 실제 관찰의 고정 규칙 |
| [T07-SUBMISSION.md](T07-SUBMISSION.md) | T07 제출 초안과 아직 채울 운영 기록 |

원문과 자료: [`source/`](source) 공식 과제 원문 · [`screenshots/`](screenshots) README용 합성 화면
(자료는 [`tools/seed_screenshot_fixture.py`](../tools/seed_screenshot_fixture.py)로 심고,
촬영은 [`tools/capture_screenshots.mjs`](../tools/capture_screenshots.mjs)로 합니다)

`docs/T06-VERIFICATION.md`는 손으로 고치지 않습니다. 기준이 바뀌면
`python tools/generate_verification.py`로 다시 만듭니다.

## 작업 기록 (`docs/process/`)

특정 시점의 인수인계·리뷰·체크리스트입니다. **기준이 아니라 기록**이므로, 여기 적힌
내용과 위 문서가 어긋나면 위 문서가 맞습니다.

| 문서 | 시점 |
|---|---|
| [HANDOFF.md](process/HANDOFF.md) | 카드 진행 중 인수인계 |
| [ACADEMY-HANDOFF-2026-09-03.md](process/ACADEMY-HANDOFF-2026-09-03.md) | **학원 PC에서 이어가기 — 최신** |
| [ACADEMY-HANDOFF.md](process/ACADEMY-HANDOFF.md) | 학원 PC에서 이어가기 (2026-09-02) |
| [HANDOFF-DESIGN-REVIEW.md](process/HANDOFF-DESIGN-REVIEW.md) | 디자인 브랜치 인수인계 |
| [REVIEW-CSS-TOKEN-LAYER.md](process/REVIEW-CSS-TOKEN-LAYER.md) | 토큰 레이어 리뷰 |
| [TODAY-CHECKLIST-2026-09-02.md](process/TODAY-CHECKLIST-2026-09-02.md) | 2026-09-02 하루 작업 |
| [T07-FINAL-SUBMISSION-CHECKLIST.md](process/T07-FINAL-SUBMISSION-CHECKLIST.md) | 2026-09-11 관찰 종료 뒤 최종 검증·배포·제출 순서 |
| [T07-DAILY-OBSERVATION-CHECK.md](process/T07-DAILY-OBSERVATION-CHECK.md) | 관찰 기간 중 매일 하는 짧은 확인 (읽기만) |
| [T07-CI-PROPOSAL-AFTER-OBSERVATION.md](process/T07-CI-PROPOSAL-AFTER-OBSERVATION.md) | 관찰이 끝난 뒤 착수할 CI 제안 (워크플로 미작성) |
| [HANDOFF-TEMPLATE.md](process/HANDOFF-TEMPLATE.md) | 인수인계 서식 |

## 지나간 문서 (`docs/archive/`)

**따르지 마세요.** 어떤 판단을 왜 접었는지 남기려고 보관만 합니다.

| 문서 | 왜 지나갔나 |
|---|---|
| [GCP-SETUP.md](archive/GCP-SETUP.md) | GCP VM 대신 Render + Neon을 선택 (D-022) |
| [T06-PRELIMINARY-ANALYSIS.md](archive/T06-PRELIMINARY-ANALYSIS.md) | 공식 과제 공개 전 사전 분석 (D-005로 대체) |
| [PROJECT-SKELETON.md](archive/PROJECT-SKELETON.md) | 구현 전 계획 골격. 실제와 다른 디렉터리를 그리고 있어 구조 안내로는 쓸 수 없습니다. 의존 방향과 작업 분할은 FLASK-ARCHITECTURE.md가 이어받았습니다 |
