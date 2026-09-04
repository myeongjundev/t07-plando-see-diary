# T07 인계 — 2026-09-04 저녁 (집에서 이어서)

> 아침 인계(`T07-HANDOFF-2026-09-04.md`)를 대체하지 않는다. **깊은 내용은 그 문서에
> 그대로 있고, 이 문서는 그 뒤로 달라진 것과 오늘 밤/내일 아침 첫 행동만 적는다.**
> 처음 읽는다면 그 문서의 0절(환경 되살리기)·4절(배포 순서)이 여전히 본문이다.

**HEAD**: `40c9c72` · 작업 트리 깨끗 · `origin/main`과 같음
**검사**: 백엔드 **304 통과 / 4 스킵** · 프런트 **71 통과** (2026-09-04 17:00 재확인)
**코드로 남은 것**: 21번(설명서) 하나뿐
**배포**: **아직 안 했다** — 아래 2절

---

## 1. 아침 인계에서 달라진 것 두 가지

### (1) C77 — 어느 T06 commit이 제출됐는가: **확정됐다**

아침 인계 3절이 "후보가 둘"이라고 남겨 둔 질문의 답이다.

**`4f3ed709d75c573beac7fc95e700c7719b53087c`**

`origin`에 푸시된 `t06-submission` 태그가 이 commit을 가리킨다. T06 저장소의 `main`도
같은 지점이고, T06 `docs/SUBMISSION.md`가 "Source URL = `t06-submission`이 가리키는
commit의 40자 URL"이라고 규정하므로 제출 폼에 들어간 해시가 이것이다.

**`1180c8d1329…`는 후보가 아니었다.** 로컬 태그가 낡아 있었을 뿐이다 — `1180c8d` 뒤로
09-03 UI 작업 commit 17개(정렬형 계획 목록, 자체 date/time picker, 게이지 baseline,
스크린샷 재촬영)가 붙었고 그것들도 전부 배포·제출본에 들어가 있다.

정리한 것과 남겨 둔 것:

- T06 저장소의 로컬 태그를 `git fetch --tags --force`로 갱신했다. 이제 `4f3ed70`을 가리킨다.
- **T07 저장소에도 `t06-submission` 태그가 있는데 그건 `1180c8d`를 가리키고, 손대지
  않았다.** 저장소를 만들 때 딸려 온 로컬 전용 사본이고 `origin`에는 없다
  (`git ls-remote --tags origin` 결과가 비어 있다). 지우려면 지워도 되지만, 지금은
  **T07 저장소의 이 태그를 근거로 삼지 말 것**만 지키면 된다.

`docs/T07-ARCHITECTURE.md` 8행과 매트릭스 C78이 적어 둔 값이 처음부터 맞았다.
C78 재확인: `git merge-base --is-ancestor 4f3ed70 HEAD` → 0.

### (2) 배포 여부 — **공개 앱으로 직접 확인했고, 안 됐다**

`https://t06-plando-see-diary.onrender.com`을 찔러 본 결과:

| 확인 | 결과 | 뜻 |
| --- | --- | --- |
| 루트 HTML의 번들 | `index-MZVl8FZ4.js` · `index-CGU0rIJc.css` | T06 `SUBMISSION.md`가 적어 둔 **T06 배포 빌드 그대로** |
| `GET /api/auth/me` | **404** | T07 인증 라우트 없음 |
| `GET /api/csrf` | **404** | 〃 |
| `GET /api/live` · `/api/health` | 200 | T06 서버가 정상 가동 중 |
| 루트 화면 | 로그인 화면 아님 | C03 미충족 |

저장소 연결이 아직 T06에 붙어 있다. 아침 인계 4절의 0~7단계 중 **아무것도 실행되지
않았다.** 5일 시계도 시작 전이다.

---

## 2. 집에서 이어갈 때 — 첫 행동은 이것 하나

### 0단계: PostgreSQL 전용 검사 3건 (배포 전 필수)

지금 스킵 중인 3개다. **한 번은 진짜 PostgreSQL에서 돌려야 배포로 넘어간다.**

**Neon에서 할 일 — 연결 문자열 복사뿐이다.**

1. Neon 콘솔 → **Branches** → 새 브랜치 → 반드시 **Branch schema only**
   (자료를 복사하는 기본 옵션으로 만들면 그 브랜치에 일기가 들어가고,
   `conftest.refuse_production`이 "행이 있다"며 거부한다 — 거부되는 게 맞다)
2. 그 브랜치 → **Connect** → 데이터베이스 `neondb` → Connection string 복사
   `postgresql://…@….neon.tech/neondb?sslmode=require`

> **SQL Editor에 명령을 붙여 넣지 말 것.** 2026-09-04에 한 번 그렇게 해서
> `syntax error at or near "TEST_DATABASE_URL"`이 났다. 아래는 SQL이 아니라 셸 명령이고,
> Neon SQL Editor는 SQL만 받는다. 명령은 **이 PC의 터미널**에서 돈다.

**PowerShell 문법으로 (아침 인계에 적힌 것은 bash 문법이라 그대로는 안 된다):**

```powershell
$env:TEST_DATABASE_URL='<복사한 연결 문자열>'; backend/.venv/Scripts/python.exe -m pytest backend/tests -q
```

끝나면 지운다:

```powershell
Remove-Item Env:TEST_DATABASE_URL
```

**통과 기준: 스킵 3개가 풀려 `307 passed`.**

- `test_deleting_a_user_removes_their_data_on_postgresql`
- `test_next_plan_link_is_cleared_rather_than_deleting_the_reflection`
- `test_a_refresh_in_flight_cannot_survive_the_change_on_postgresql`

> ⚠️ `TEST_DATABASE_URL`에 **프로덕션 URL을 넣지 말 것.** 이 검사들은 그 데이터베이스의
> 모든 표를 지운다. `conftest.refuse_production`이 막지만, 막는 것에 기대지 말 것.

### 1단계 이후: 아침 인계 4절 「그날 순서」 그대로

0단계가 통과하면 그 표의 1~7번을 순서대로 따라간다. 이 문서에 옮겨 적지 않는다 —
옮기다 흔들리는 것이 이 프로젝트에서 가장 자주 낸 사고다.

**가기 전에 Neon 스냅샷 하나.** claim은 빈 T06 데모 계획 4개를 **삭제**하고,
저장소 연결을 되돌려도 그건 안 돌아온다.

---

## 3. 일정 — 왜 배포를 미루면 안 되는가

5일 실사용 기록(C07)은 **잠긴 앱**으로, **배포 다음 날부터** 서로 다른 달력 5일이
필요하다. **코드로 앞당길 수 없는 유일한 기준이다.**

| 배포한 날 | 5일 기록 |
| --- | --- |
| 09-04 (오늘) | 09-05 ~ 09-09 |
| 09-05 | 09-06 ~ 09-10 |
| 하루 밀릴 때마다 | 전부 하루씩 밀린다 |

21번 설명서는 **5일이 도는 동안 쓰면 된다.** 순서는 언제나 배포 먼저다.

---

## 4. 남은 작업 전체

| | 무엇 | 상태 |
| --- | --- | --- |
| 0 | PostgreSQL 검사 3건 | **다음 행동** |
| 1 | Neon 스냅샷 | |
| 2 | 배포 (아침 인계 4절 1~7) | |
| 3 | 5일 기록 시작 | 배포 다음 날 |
| 4 | 21번 — 설명서 여섯 항목 `docs/T07-AUTH-GUIDE.md` | 파일 아직 없음. 5일 도는 동안 |
| 5 | 확인 4줄(C39) · 판단 3줄(C40) | C40은 **본인이 쓴다** |

21번을 쓸 때 이미 있는 재료:

- ⑥ 「아직 못 막은 것」 → `docs/T07-ARCHITECTURE.md` **11절 14개 항목**이 단일 소스다.
  설명서에 두 번째 목록을 만들지 말 것 — 갈라진다
- ③ 네 흐름의 소스 경로 → 설계 3절이 뼈대
- ④ 확인 기록 → `docs/T07-EVIDENCE/01`~`11` (전부 스크립트가 찍은 것)
- ② 왜 골랐나 → `docs/process/T07-AUTH-DIRECTION-2026-09-03.md` · `docs/T07-AUTH-OPTIONS.md`
- **C77에 적을 40자**: `4f3ed709d75c573beac7fc95e700c7719b53087c`
- `docs/T07-AUTH-ARCHITECTURE-TARGET.md`는 **배포된 것의 설명이 아니다.**
  Google OAuth2는 붙지 않았다. 설명서에 그 문서를 근거로 "막았습니다"를 적지 말 것

---

## 5. 집 PC에서 처음이라면

아침 인계 0절 그대로다. 요약:

```powershell
git clone https://github.com/myeongjundev/t07-plando-see-diary
py -3 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]" argon2-cffi bcrypt
npm --prefix frontend install
```

셋 다 통과해야 이어간다:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests   # 304 passed, 4 skipped
npm --prefix frontend test                                  # 71 passed
npm --prefix frontend run build
```

화면을 보려면 Vite 개발 서버(5173) 말고 **한 출처로 내는 쪽**을 쓴다 — 쿠키·SameSite·
`__Host-` 접두사가 전부 출처에 달려 있어서 프록시 상태로는 세션을 확인할 수 없다.

```powershell
npm --prefix frontend run build
backend/.venv/Scripts/python.exe backend/local_server.py   # http://127.0.0.1:5099
```
