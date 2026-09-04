# T07 설계 — 잠금 구조

상태: **인증 조합 확정(2026-09-03), 설계 리뷰 반영. ▢ 표시 한 곳만 측정 대기 — Argon2id 매개변수.**

권위 있는 원문: `docs/source/T07-OFFICIAL-ASSIGNMENT.md`
방향 결정: `docs/process/T07-AUTH-DIRECTION-2026-09-03.md`
판단 재료: `docs/T07-AUTH-OPTIONS.md`
이어받은 T06: commit `4f3ed709d75c573beac7fc95e700c7719b53087c` (T07-C77 · C78)

이 문서는 "무엇을 만들지"가 아니라 **"채점자가 읽을 장면을 어떤 구조가 만들어 내는지"** 를
적는다. 통과 기준 하나하나가 코드의 어느 지점에서 나오는지 미리 못 박아 두고, 구현은
그 지점을 채우는 일이 된다.

보안 항목 하나마다 **왜 필요한가 · 어떻게 막는가 · 막혔다는 증거**를 같이 남긴다.
증거 없이 "막았습니다"라고 적은 항목은 이 문서에 없다.

---

## 0. 저장소와 배포를 새로 만든 방식

빈 저장소가 아니라 **T06 저장소를 복제해서** 시작했다. T07-C78이 "T07 소스 이력에 제출
당시의 고정 T06 commit이 조상으로 포함"을 요구하기 때문이다. 확인:

```
git merge-base --is-ancestor 4f3ed70 HEAD   # 종료 코드 0
```

원격은 <https://github.com/myeongjundev/t07-plando-see-diary> (public).

**배포는 T06 것을 그대로 이어받는다.** 서비스도 데이터베이스도 새로 만들지 않는다
(2026-09-03 결정). 기존 Render 서비스의 저장소 연결을 T07로 돌리고, Neon도 그대로 쓴다.

얻는 것: 주소가 유지되고, **C100 이관이 공짜가 된다.** T06 행이 이미 옳은 데이터베이스에
있으므로 덤프·복원 없이 `claim_t06_data`만 돌리면 된다. `plans.user_id`를 NOT NULL로
조이는 것도 그대로 간다 — 저장소를 돌리는 순간 T06 앱은 더 이상 이 DB를 쓰지 않으므로,
NOT NULL이 깨뜨릴 상대가 없다.

대가는 **순서 하나로 치른다.** 저장소를 돌리는 순간
`t06-plando-see-diary.onrender.com`이 로그인 화면이 되는데, T06 기준은 그 주소가 로그인
없이 열릴 것을 요구한다.

> **막는 문(gate): T06을 제출 폼에 넣기 전에는 저장소를 돌리지 않는다.**
> 2026-09-03 현재 T06은 배포·태그까지 끝났고 제출만 남았다(`docs/SUBMISSION.md`).
> 제출이 끝난 뒤에 돌린다.

남는 위험도 적어 둔다: 제출 뒤에 채점자가 T06 주소를 다시 열면 로그인 화면을 본다.
주소 하나를 두 과제가 나눠 쓰는 데서 오는 값이고, **알고 고른 것**이다.

### Render Free에는 셸이 없다

대시보드 Shell도 SSH도 일회성 잡도 크론도 Free에는 없다. **인스턴스에서 도는 코드는 웹
서비스 프로세스 하나뿐이다.** 그래서 일회성 명령(해싱 벤치마크, T06 자료 이관)은
`deploy/start.sh`의 `BOOT_TASK`로 **부팅에 얹어 보내고 로그로 받는다**. 고정 목록 대조,
백그라운드 실행, 엔드포인트 없음. 절차와 제거 방법은
`docs/T07-EVIDENCE/00-hash-bench-render-runbook.md`.

---

## 1. 무엇으로 붙이는가 — **확정**

| 층 | 고른 것 | 한 줄 이유 |
| --- | --- | --- |
| ① 비밀번호 보관 | **Argon2id** (`argon2-cffi`) | 메모리 하드라 GPU 대입이 메모리 대역폭에 막힌다. 소금·매개변수를 해시 문자열 안에 스스로 담아 내가 손댈 여지가 없다 |
| ② 사람을 기억하는 법 | **짧은 수명 JWT Access + 회전하는 불투명 Refresh** (하이브리드) | 오래 사는 자격증명은 좁은 경로로만 오가고, 넓게 오가는 자격증명은 10분만 산다 |
| ③ 세션 운반 | **HttpOnly·Secure 쿠키 두 개 + 읽을 수 있는 CSRF 쿠키 하나** | 값이 주소창에 실리지 않고(C112), JS가 인증값 원문을 읽지 못한다 |

즉 답은 **"비밀번호는 라이브러리, 세션은 직접 구현"** 이고, 설명서 ①에는 이 둘을 갈라서
적는다. C107은 *비밀번호를 다루는 부분*만 라이브러리를 요구하므로 이 조합이 기준을
벗어나지 않는다.

### ▢ Argon2id 매개변수 — 측정 대기

노트북 표는 결정 근거가 못 된다(CPU 기준점 57.1ms인 기계). 배포 인스턴스(0.1 코어)에서
`BOOT_TASK`로 다시 재고, **검증 500ms 예산 안에서 가장 비싼 설정**을 고른다.

- 하한: OWASP 최소 권장 `m=19456KiB, t=2, p=1`
- 상한을 누르는 것: 512MB 인스턴스. `p=1`이라도 동시 로그인 두 건이면 선언 메모리의 두 배.
  `m`을 47MiB로 올리면 두 건에 94MiB — 여유는 있지만 공짜는 아니다.
- 단일 검증 평균만 재지 않는다. 후보마다 **단일 p50/p95, 동시 2건·4건의 wall time과
  프로세스 peak RSS**를 같이 잰다. 500ms는 목표이지, OOM 위험을 무시하고 가장 큰 `m`을
  고르라는 규칙이 아니다.
- 결과는 `docs/T07-EVIDENCE/00-hash-bench-render.md`, 확정값은 이 표에 채운다.
- **값이 들어갈 자리는 이미 코드에 있다.** `app/security/passwords.py`가 매개변수를
  환경변수 `ARGON2_TIME_COST` · `ARGON2_MEMORY_KIB` · `ARGON2_PARALLELISM`에서 읽고,
  없으면 OWASP 최소값으로 돈다. 측정이 끝나면 `render.yaml` 세 줄이 바뀌고 코드는
  그대로다. 매개변수를 올려도 기존 계정이 잠기지 않는다 — 로그인 때
  `check_needs_rehash`로 옛 해시를 알아보고 그 자리에서 다시 만든다.

### 하이브리드를 고른 이유 — 그리고 그 대가

두 자격증명의 성질이 다르다는 것이 요점이다.

| | Access | Refresh |
| --- | --- | --- |
| 형식 | JWT (HS256) | 불투명 난수 `secrets.token_urlsafe(32)` |
| 수명 | **10분** | 유휴 48시간 / 절대 14일 |
| 어디로 다니나 | 모든 API 요청 (`Path=/`) | **`/api/auth`에만** |
| DB 저장 | 저장하지 않음 | **SHA-256만** |
| 훔치면 | 10분치 | 한 번 쓰는 순간 재사용이 탐지된다 |

**넓게 다니는 값은 짧게 살고, 오래 사는 값은 좁게 다닌다.** 이 교환이 하이브리드의 값어치다.

대가는 정직하게 적는다. **무상태라는 이점은 포기한다** — 아래 C114 때문에 Access 검증도
DB를 한 번 읽는다. 남는 값어치는 (1) 서명과 `exp`가 토큰 안에 있어 DB 행이 새도 토큰을
만들 수 없다는 것, (2) Refresh 회전·재사용 탐지가 붙을 자리가 생긴다는 것 두 가지다.
"DB를 안 읽어서 빠르다"는 이 설계의 이유가 **아니다.**

2026-09-03 설계 리뷰 판정도 남긴다: 고정 통과 기준과 5일 일정만 보면 단일 불투명 서버
세션이 더 작고 정직하다. JWT는 이 구조에서 성능 이점을 주지 않는다. 그래도 사용자가 정한
보안 포트폴리오 방향인 회전·재사용 탐지를 유지하기 위해 하이브리드를 보존한다. 그 선택은
아래의 DB 행 잠금, C114 경합 검사, 탭 간 refresh 직렬화를 **선택 사항이 아니라 필수 비용**으로
만든다. 일정이 다시 막히면 고급 항목을 반쯤 구현하는 대신 단일 불투명 세션으로 되돌리는
것이 정해 둔 축소안이다.

### C114가 무상태 JWT를 잘라 낸다 — `sid` 바인딩

> T07-C114 — 비밀번호를 바꾸거나 로그아웃하면 **이전에 발급한 값이 더는 통하지 않는다.**
> T07-C109 — 로그아웃한 뒤 **같은 값으로** 다시 요청했을 때의 거절 응답.

Access JWT를 순수 무상태로 두면 로그아웃 뒤에도 **최대 10분 더 통한다.** C114는 조건 없이
"더는 통하지 않는다"라고 쓰여 있으므로, 이건 문서로 양해를 구할 수 있는 창(window)이
아니라 **기준 위반**이다.

그래서 Access JWT에 `sid`(refresh session id) 클레임을 넣고, 가드가 매 요청 그 세션 행의
`revoked_at`·`expires_at`·`last_used_at`을 확인한다. 로그아웃·비밀번호 변경이 그 행을
건드리는 순간 **다음 요청부터 즉시** 거절된다.

이 문단은 그대로 설명서 ②에 들어간다. "무상태 JWT는 즉시 폐기와 원리적으로 양립하지
않는다"는 것이 이 과제에서 실제로 만들어 보고 알게 된 것이다.

### 검토했지만 고르지 않은 것 (C93)

- **인증 서비스(Auth0·Supabase Auth·Clerk)** — 비밀번호 해시가 남의 서버에 남아서,
  "내 데이터베이스에 저장된 비밀번호 값"(C103)과 "같은 비밀번호로 만든 두 계정의 저장된
  값이 다름"(C104)을 **제출문에 보일 방법이 없다**. 카드 2를 통째로 포기하는 셈이다.
- **Flask-Login 기본 세션(서명 쿠키)** — 로그아웃이 브라우저 쿠키를 지울 뿐이라, 그
  쿠키를 그대로 다시 보내면 서버가 여전히 받아 준다. C109·C114 장면이 나오지 않는다.
- **순수 무상태 JWT** — 위와 같은 이유로 C114에서 탈락.
- **Refresh 없는 단일 불투명 세션 쿠키** — 기준은 전부 통과한다. 고르지 않은 이유는
  회전·재사용 탐지가 붙을 자리가 없어서다. 즉 이건 **기준이 아니라 이 과제의 목적
  (보안 포트폴리오)** 때문에 갈린 선택이고, 그렇게 적는다.

---

## 2. 데이터 구조

### 새 표 네 개

```sql
users
  id                    uuid pk
  email                 citext unique not null   -- 소문자로 정규화해 저장
  password_hash         text not null            -- argon2id 인코딩 문자열
  password_changed_at   timestamptz not null
  created_at / updated_at
  -- 비밀번호 원문·힌트·질문 없음

refresh_sessions
  id              uuid pk                        -- Access JWT의 sid 클레임이 가리키는 값
  user_id         uuid not null references users(id) on delete cascade
  family_id       uuid not null                  -- 로그인 한 번 = 계열 하나
  token_sha256    char(64) unique not null       -- 원본 토큰은 저장하지 않는다
  issued_at       timestamptz not null
  last_used_at    timestamptz not null           -- 유휴 만료의 기준. 회전할 때만 갱신
  expires_at      timestamptz not null           -- 절대 만료. 계열 전체가 같은 값을 물려받는다
  revoked_at      timestamptz null
  revoked_reason  text null                      -- logout | rotated | reuse | password_change | account_delete
  replaced_by_id  uuid null references refresh_sessions(id)
  index (family_id)

login_attempts
  id                bigserial pk
  email_normalized  citext null      -- 존재하지 않는 계정도 센다 (안 그러면 세는 것 자체가 존재를 알린다)
  ip_hash           char(64) not null -- HMAC-SHA-256(IP_HASH_SECRET, canonical_ip)
  result            text not null     -- failure | blocked | success. 잠금 계산은 failure만 센다
  attempted_at      timestamptz not null
  index (email_normalized, attempted_at desc)
  index (ip_hash, attempted_at desc)

security_events
  id            bigserial pk
  event_type    text not null
  result        text not null
  user_id       uuid null references users(id) on delete set null
  session_id    uuid null
  ip_hash       char(64) null
  created_at    timestamptz not null
  metadata      jsonb not null default '{}'
  index (created_at desc), index (event_type, created_at desc)
```

**세션 토큰을 그대로 저장하지 않는 이유**: 데이터베이스가 새면 그 값으로 곧장 로그인이
된다. 비밀번호와 같은 이유로 해시만 둔다. 다만 토큰은 256비트 난수라 사전 공격 대상이
아니므로 Argon2가 아니라 SHA-256으로 충분하다 — 이 판단도 설명서에 적는다.

**`last_used_at`을 회전할 때만 갱신하는 이유**: 유휴 만료를 매 요청 기록하면 요청마다 쓰기가
한 번 붙는다. Refresh 회전은 Access TTL(10분)마다 한 번 일어나므로, 그 자리에 적으면
유휴 판정의 해상도가 10분이 되고 쓰기는 10분에 한 번이 된다. **해상도 10분이면 48시간
유휴 만료에 충분하다.** 여기서 유휴는 "사람의 입력이 없었음"이 아니라 **인증된 API 활동이
없었음**이다. 백그라운드 폴링은 두지 않는다. 나중에 폴링을 넣으면 그것이 세션을 살리지
않도록 별도 정책을 먼저 정한다.

**`security_events.user_id`가 `on delete set null`인 이유**: C134가 계정과 자료를 함께
지우라고 한다. 사건 기록까지 지우면 "털린 뒤에 알아낼 방법"이 사라지고, 남겨 두면 지운
계정의 흔적이 남는다. 사람을 가리키는 열만 끊고 사건은 남기는 것이 두 요구를 다 지킨다.
`metadata`에는 이메일, 사용자 ID, 자료 ID처럼 삭제된 사람을 다시 식별할 값도 넣지 않는다.
계정 삭제 뒤 `user_id IS NULL`과 metadata 비식별 상태를 함께 검사한다.

**잠금 표를 따로 두지 않는 이유**: 잠금은 `login_attempts`의 최근 실패 건수에서 **파생**한다.
상태를 두 곳에 두면 어긋나는 날이 오고, 그때 어느 쪽이 참인지 코드가 답할 수 없다.

### 기존 표에 붙는 것

`plans.user_id`(FK, NOT NULL)를 **소유권의 유일한 뿌리**로 둔다. tasks·executions·
reflections·plan_revisions는 `user_id`를 따로 갖지 않고 **plans를 거쳐 주인을 판정**한다.

> 비정규화(각 표에 user_id 복사)를 하지 않는 이유: 두 곳에 적힌 주인이 어긋나는 순간
> 어느 쪽이 참인지 코드가 답할 수 없다. 조인 한 번이 그 위험보다 싸다.

기존 FK도 계정 삭제에 맞춰 고친다. `reflections.plan_id`는 `on delete cascade`,
`reflections.next_plan_id`는 `on delete set null`로 한다. 지금 두 FK는 삭제 동작이 없어
`users → plans` cascade를 PostgreSQL이 중간에서 막는다. 계정 삭제 자동 검사는 SQLite의
ORM cascade만 보지 않고 PostgreSQL FK 동작까지 확인한다(C134).

소유권은 단건 가드만의 일이 아니다. 다음 네 갈래를 각각 사용자 범위로 만든다.

- 단건: `owned_plan` / `owned_task` / `owned_reflection` — 못 찾으면 항상 404
- 목록·집계: `plans_for(user)`와 plan 소유권을 먼저 고정한 하위 쿼리
- 생성: `create_plan(user, ...)`와 "다음 계획"을 포함한 모든 Plan 생성에 `user_id` 필수
- 내보내기: 같은 repeatable-read snapshot 안에서 **그 사용자의 plan 집합에 조인된 행만** 출력

따라서 "기존 서비스 계층은 그대로 두고 데코레이터 두 줄만 붙인다"는 접근은 쓰지 않는다.
목록과 export는 ID 한 건을 받지 않으므로 단건 가드만으로 격리할 수 없다(C123·C125·C133).

### T06 자료를 내 계정으로 옮기기 (C100)

세 단계 이관으로, 중간 상태를 한 배포 안에 숨기지 않는다.

1. `user_id`를 **nullable로 추가**
2. `backend/scripts/claim_t06_data.py` — 환경변수로 받은 이메일·비밀번호로 계정을
   만들고, `UPDATE plans SET user_id = :id WHERE user_id IS NULL` 실행
3. `NULL=0` 로그를 확인한 **다음 배포의 별도 마이그레이션**에서 NOT NULL로 조인다

`deploy/start.sh`는 `flask db upgrade`를 BOOT_TASK보다 먼저 실행한다. 그러므로 nullable
추가와 NOT NULL 변경을 같은 배포에 넣으면 claim 전에 마이그레이션이 실패한다. 실제 순서는
**(A) nullable+claim 배포 → (B) claim 건수와 `NULL=0` 확인 → (C) NOT NULL 배포**다.
claim은 한 트랜잭션이고 재실행해도 같은 결과여야 한다. `deploy/start.sh`에서 오래 걸리는
벤치마크만 백그라운드로 두고, **claim은 마이그레이션 뒤·waitress 앞에서 동기 실행**한다.
그러면 새 인스턴스가 `/api/live`를 열기 전에 주인이 붙고, 평상시 liveness는 계속 DB를
읽지 않는다. claim은 해시 한 번과 UPDATE라 벤치마크처럼 수 분짜리 작업이 아니다.

셸이 없으므로 이 스크립트도 `BOOT_TASK`로 태워 보낸다. **비밀번호는 `BOOT_TASK_ARGS`가
아니라 별도 환경변수(`sync: false`)로 받는다** — `render.yaml`은 커밋되는 파일이고, 인자로
넘기면 로그의 명령줄에도 남는다.

T06 데이터베이스를 그대로 물려받으므로(0절) **옮길 자료는 이미 제자리에 있다.** 이관은
"주인을 붙이는" 일뿐이고, 덤프·복원 단계가 없다.

옮기지 않을 합성 자료는 제목이나 본문 문자열로 판정하지 않는다. 배포 DB를 먼저 읽어 만든
**고정 ID 허용/제외 목록**으로 가르고, 실제 T06 자료는 전부 같은 계정에 붙인다. 스크립트는
옮긴 ID와 제외한 ID의 건수만 출력하고 사용자 문장은 로그에 내지 않는다.

---

## 3. 요청이 지나는 길 (설명서 ③의 뼈대 · C128)

```
보호 자원 요청
 └ app/auth/guards.py : @login_required
      __Host-pds_access 쿠키 → JWT 서명·exp 검증      → 실패 401
      sid로 refresh_sessions 조회
        없음 / revoked_at 있음                        → 401
        expires_at 지남 (절대 14일)                   → 401
        last_used_at + 48시간 지남 (유휴)             → 401
      통과하면 g.current_user · g.session 을 채운다
 └ app/auth/csrf.py : @csrf_protect          (상태를 바꾸는 메서드에만)
      Content-Type ≠ application/json                  → 415
      헤더 X-CSRF-Token 없음                          → 403
      헤더 ≠ __Host-pds_csrf 쿠키                     → 403
 └ app/services/ownership.py : owned_plan(id) / owned_task(id) / owned_reflection(id)
      select(...).join(Plan).where(Plan.user_id == g.current_user.id)
      한 건이라도 못 찾으면 → 404 (있는데 남의 것 / 아예 없음을 구별해 주지 않는다)
 └ 사용자 범위가 필요한 서비스 계층 (단건·목록·집계·생성·export)
```

거절을 만드는 자리는 **이 세 파일뿐이다.** C126에서 "거절을 만들어 내는 소스 위치"로
가리킬 곳이 한 군데로 모이도록 일부러 이렇게 나눈다. API 함수 안에서 각자 주인을
확인하게 두면, 나중에 한 곳을 빠뜨렸을 때 그것을 찾을 방법이 없다.

보호 자원에서는 `@login_required`가 **먼저**다. CSRF가 먼저 세션 행을 찾으려 하면 인증을
중복 구현하게 되고, 미로그인 상태 변경 요청이 401 대신 403을 받아 거절 규격도 흔들린다.
가입·로그인은 아직 세션과 CSRF 쿠키가 없으므로 예외다. 두 엔드포인트는 JSON만 받고
`Origin`을 배포 origin의 allowlist와 대조한다. 브라우저의 교차 출처 JSON 요청은 preflight를
거치며 CORS를 열지 않는다. `/api/auth/refresh`는 불투명 Refresh를 먼저 검증한 뒤 일반
이중 제출 검사를 한다. **세션이 생기기 전과 Access가 만료된 뒤의 인증 경로를 일반 보호
자원 데코레이터에 억지로 넣지 않는다.**

### 새 엔드포인트

| 메서드·주소 | 하는 일 | 관련 기준 |
| --- | --- | --- |
| `POST /api/auth/signup` | 계정 생성 | C94 · C98 |
| `POST /api/auth/login` | 계열 생성, 쿠키 세 개 심기 | C95 · C99 |
| `POST /api/auth/refresh` | **회전**: 옛 행 revoke, 새 행 발급, 새 Access | C111 |
| `POST /api/auth/logout` | 그 세션 revoke, 쿠키 삭제 | C96 · C109 |
| `GET  /api/auth/me` | 현재 사용자 | 프런트 게이트 |
| `POST /api/auth/password` | 비밀번호 변경 + **그 사용자 전 세션 폐기** | C114 |
| `DELETE /api/account` | 계정과 자료 함께 삭제 | C134 |
| `GET  /api/export` | **내 자료만** 파일 하나로 | C133 · C125 |

`GET /api/live`는 Render의 무인증 health check이므로 가드를 붙이지 않고 DB도 읽지 않는다.
`GET /api/health`의 공개 범위도 별도로 유지한다. "기존 22개 전부"가 아니라 **사용자 자료를
읽거나 바꾸는 기존 엔드포인트**에 인증을 붙인다. Render는 health check의 4xx를 실패로
판정하므로 `/api/live`의 200은 배포 전제다.

기존 T06 사용자 자료 엔드포인트는 주소를 바꾸지 않는다. 단건은 `@login_required` +
`owned_*`, 목록·집계·export는 2절의 사용자 범위 쿼리를 쓴다. 주소가 그대로여야
"T06에서는 열리던 것이 T07에서는 401"이라는 장면이 같은 주소로 찍힌다.

### 거절 규격 (C121)

| 상황 | 응답 |
| --- | --- |
| 로그인 안 함 · 만료 · 폐기됨 | `401` `{"error":{"message":"로그인이 필요합니다."}}` |
| CSRF 없음/불일치 | `403` `{"error":{"message":"요청을 확인할 수 없습니다."}}` |
| 남의 자료 | `404` — **403이 아니다** |
| 아이디 없음 / 비밀번호 틀림 | `401` `{"error":{"message":"이메일 또는 비밀번호가 올바르지 않습니다."}}` — **두 경우 완전히 같은 문자열·같은 코드** (C99) |
| 시도 제한 걸림 | `429` — 계정 존재 여부와 무관하게 같은 문구 (6절) |

404를 고르는 이유: 403은 "그 ID는 있다"를 알려 준다. 남의 계획 ID를 훑어 존재 여부만
모으는 일을 막으려면 없는 것과 구별되지 않아야 한다. C121이 명시적으로 허용한다.

**아이디 없음일 때도 Argon2 검증을 한 번 헛돌린다.** 안 그러면 응답 시간이 달라 아이디
존재 여부가 새어 나가, 문구를 같게 맞춘 뜻이 없어진다. 고정 더미 해시를 모듈 상수로 두고
그것을 검증한다.

---

## 4. 토큰과 세션 규칙

### Access — JWT

- 알고리즘 **HS256**. 서명 비밀키는 `JWT_SECRET`.
- 클레임은 **최소한만**: `sub`(user id) · `sid`(refresh session id) · `iat` · `exp` · `jti`.
- **넣지 않는 것**: 비밀번호, 비밀번호 해시, refresh 토큰, 비밀키, 이메일, 이름, 기타
  개인정보. JWT payload는 Base64일 뿐 암호문이 아니다 — 누구나 읽는다.
- TTL **10분**.

### Refresh — 불투명 난수 + 회전

- `secrets.token_urlsafe(32)` = **256비트**. `random`이 아니라 `secrets`인 이유: `random`은
  메르센 트위스터라 출력 몇 개로 내부 상태가 복원된다. `secrets`는 OS 난수원이다.
- DB에는 `SHA-256`만. 브라우저에는 원문을 준다.
- **정상 흐름**:

```
Refresh A → /api/auth/refresh → A 검증 → A.revoked_at 기록(reason=rotated)
                                       → B 발급, A.replaced_by_id = B
                                       → 새 Access JWT (sid = B)
```

  하나의 Refresh 토큰은 **정상적으로 한 번만 쓰인다.**

- **회전은 한 트랜잭션이다.** A revoke, B insert, `replaced_by_id` 연결을 함께 commit한다.
  두 요청이 A를 동시에 읽으면 B와 C가 둘 다 생기거나 정상 동시 요청을 재사용으로 오판한다.

  **구현은 `SELECT ... FOR UPDATE`가 아니라 조건부 UPDATE로 했다**(2026-09-03).
  `UPDATE ... WHERE token_sha256 = :d AND revoked_at IS NULL`의 `rowcount`가 1인 쪽만
  이긴다. 바꾼 이유는 **SQLite가 `FOR UPDATE`를 무시하기** 때문이다 — 두 요청이 A를 살아
  있는 것으로 읽고 둘 다 후계를 만들어 계열이 갈라진다. 검사가 그것을 잡아냈다
  (`test_concurrent_use_of_one_token_yields_exactly_one_successor`). 조건부 UPDATE는 행
  잠금이 필요 없고 **두 엔진 모두에서 원자적**이라, 검사가 PostgreSQL에서만 의미 있는
  상태를 벗어난다.

  사용자 행 `FOR UPDATE`는 그대로 둔다. 비밀번호 변경과의 순서를 맞추는 데 필요하고,
  그건 경쟁이 아니라 직렬화라 SQLite의 쓰기 직렬화로도 같은 결과가 난다.
- Access의 `sub`는 세션 행의 `user_id`와 반드시 같아야 한다. 이후 권위 있는 사용자 ID는
  JWT 문자열이 아니라 DB 행에서 가져온다.
- 비밀번호 변경은 사용자 행을 잠근 채 비밀번호 갱신과 전 세션 revoke를 commit한다.
  Refresh도 같은 사용자 행 잠금을 거친다. 그래야 "A 검증 → 비밀번호 변경 revoke → B insert"
  순서로 옛 자격증명에서 새 세션이 살아나는 C114 경합이 없다. 로그아웃과 같은 sid의
  Refresh도 세션 행 잠금으로 직렬화한다.

- **재사용 탐지**: 이미 `revoked_at`이 찍힌 행의 토큰이 다시 오면, 그 토큰은 회전 시점과
  지금 사이에 **복제됐다는 뜻**이다. 정상 사용자와 공격자 중 누가 보냈는지는 알 수 없으므로
  **둘 다 끊는다**:

```
같은 family_id의 refresh_sessions 전부 revoke (reason=reuse)
security_events: REFRESH_TOKEN_REUSE_DETECTED
401
```

  계열 전체를 끊는 것이 요점이다. 그 토큰 하나만 끊으면 공격자가 이미 받아 간 B가 살아
  있다. 결과적으로 정상 사용자도 재로그인해야 하지만, **탈취를 눈치채지 못한 채 공유되는
  것보다 낫다.**

### 만료 두 겹 (C111)

| | 값 | 무엇을 막나 |
| --- | --- | --- |
| Access TTL | **10분** | 훔친 Access 쿠키의 수명 |
| 유휴 (idle) | **48시간** | 쓰지 않는 기기에 남은 세션 |
| 절대 (absolute) | **14일** | 계속 회전시키며 무기한 사는 세션 |

절대 만료는 **계열 단위**다. 회전해도 `expires_at`은 물려받아 늘어나지 않는다. 안 그러면
"절대"가 아니다.

C111에 적을 한 문장: **"Access 토큰은 10분, 로그인 세션은 48시간 쓰지 않으면 끊기고,
계속 써도 발급 후 14일에 반드시 끊긴다."**

### 쿠키 세 개 (③ · C112)

| 이름 | HttpOnly | SameSite | Path | 왜 |
| --- | --- | --- | --- | --- |
| `__Host-pds_access` | ✅ | Lax | `/` | 모든 요청에 붙어야 한다. 외부 링크로 들어와도 로그인 상태여야 하므로 Lax |
| `__Secure-pds_refresh` | ✅ | **Strict** | `/api/auth` | 우리 화면의 XHR로만 오간다. 최상위 이동이 없으니 Strict가 손해 없이 더 세다 |
| `__Host-pds_csrf` | ❌ | Lax | `/` | JS가 **읽어서 헤더에 실어야** 하므로 HttpOnly가 아니다. 인증값이 아니라 확인값이다 |

전부 `Secure`. 토큰은 **쿼리스트링·경로에 절대 넣지 않는다**(C112).

`Secure`를 끄는 곳은 **테스트 클라이언트 하나뿐**이다(`TESTING` 기준). 처음에는
`REQUIRE_POSTGRES`로 갈랐는데, 그러면 로컬 개발에서 `Secure`가 빠지고 —
브라우저는 `Secure` 없는 `__Host-` 쿠키를 **스킴과 무관하게 거부한다.** 개발 중
로그인이 아무 말 없이 아무것도 저장하지 않았다. 브라우저는 `http://localhost`에
한해 `Secure` 쿠키를 받아 주므로, 켜 둔 채로 개발 서버가 정상 동작한다.

**접두사 판단.** `__Host-`는 `Path=/`를 강제하므로 refresh 쿠키에는 쓸 수 없다 — 경로를
좁히는 쪽이 더 값어치 있다고 보고 `__Secure-`를 골랐다. 접두사가 원래 막는 위협은
형제 서브도메인의 쿠키 덮어쓰기인데, **`onrender.com`은 Public Suffix List에 등재돼
  있어**(2026-09-03 확인, PSL 15408행) 브라우저가 `Domain=.onrender.com` 쿠키를 아예
  거부한다. 즉 이 호스트에서는 접두사가 결정적이지 않다. 그래도 붙이는 이유는 나중에
  자체 도메인으로 옮겼을 때 조용히 약해지지 않게 하기 위해서다.

### 비밀키 (C113)

T06에는 비밀키가 하나도 없었다. JWT를 넣으면서 `JWT_SECRET`이 생기므로, **없음을
증명해야 하는 대상이 생겼다.** 이게 하이브리드의 두 번째 대가다.

- `render.yaml`에서 `JWT_SECRET`과 `IP_HASH_SECRET`을 `generateValue: true`로 둔다 —
  **Render가 만든다.** 값이 git에도, 내
  기계에도, 이 대화에도 존재한 적이 없다.
- 프런트 번들에 들어갈 경로가 없다: 서명·검증은 전부 서버에서만 일어난다.
- `backend/scripts/audit_secrets.py`에 JWT **값** 모양(`eyJ`로 시작하는 3토막)을 추가해
  빌드 산출물·문서·git 이력을 계속 훑는다. 쿠키 **이름**은 소스와 문서에 있어야 하며
  비밀이 아니므로 탐지 대상으로 삼지 않는다. 검사는 "어디에도 없음"이라는 무한한 주장이
  아니라 워킹트리·빌드 산출물·Git 이력·수집한 응답과 로그라는 범위를 함께 적는다.
- 폐기 절차도 적어 둔다: `JWT_SECRET`을 갈면 발급된 Access가 전부 무효가 되고, Refresh는
  살아 있으므로 사용자는 다음 회전에서 조용히 회복한다. **이건 설계의 성질이지 우연이 아니다.**

### 폐기 경로

| 사건 | 끊기는 범위 | reason |
| --- | --- | --- |
| 로그아웃 | 그 세션 하나 | `logout` |
| 회전 | 옛 행 하나 | `rotated` |
| 재사용 탐지 | **계열 전체** | `reuse` |
| 비밀번호 변경 | **그 사용자의 모든 계열** | `password_change` |
| 계정 삭제 | cascade | — |

로그아웃은 쿠키만 지우고 끝내지 않는다. 서버 행을 먼저 revoke하고 그다음 쿠키를 지운다.
**순서가 이래야** 쿠키 삭제 응답이 유실돼도 세션은 이미 죽어 있다.

---

## 5. CSRF — 세 겹, 서버 세션 바인딩은 하지 않는다

쿠키 인증이라 교차 사이트 요청이 붙을 수 있다. 상태를 바꾸는 메서드
(`POST`·`PUT`·`PATCH`·`DELETE`)는 세 겹을 전부 통과해야 한다.

1. **`SameSite`** — 남의 사이트의 폼 POST가 쿠키를 달고 가지 못한다.
2. **`Content-Type: application/json` 요구** — 브라우저가 교차 출처로 이 헤더를 붙이려면
   프리플라이트를 거쳐야 하고, CORS를 열지 않았으므로 막힌다.
3. **`__Host-` 이중 제출 토큰** — 아래.

### 왜 세션 행과 대조하지 않는가

순수 이중 제출(쿠키 값 == 헤더 값)은 **공격자가 쿠키를 심을 수 있으면 뚫린다.** 자기가
아는 값을 쿠키와 헤더 양쪽에 넣으면 두 값이 일치하기 때문이다. 이 설계의 CSRF 쿠키는
`__Host-`라 `Secure`, host-only, `Path=/`가 브라우저에서 강제된다. `onrender.com`도 PSL이라
형제 서비스가 Domain 쿠키를 심지 못한다. 반대로 같은 출처 XSS가 난 상황이면 공격자는
진짜 CSRF 쿠키를 이미 읽어 대신 요청할 수 있으므로 DB 바인딩이 추가로 막는 것이 없다.

세션 바인딩은 방어 이득 없이 세 가지 고장을 만든다: 세션이 없는 signup/login의 bootstrap,
Access가 만료된 refresh의 검사 순서, 회전 중 CSRF 쿠키 교체와 진행 중 요청의 경합. 그래서
CSRF 확인값은 서버 DB에 저장하지 않고 로그인할 때 한 번 만들며, 같은 로그인 상태에서는
refresh 때 바꾸지 않는다.

```
로그인 시:         csrf = secrets.token_urlsafe(32)
                 Set-Cookie: __Host-pds_csrf=csrf   (HttpOnly 아님, SameSite=Lax)

보호 요청 시:     X-CSRF-Token 헤더 == __Host-pds_csrf 쿠키
signup/login:     application/json + 허용된 Origin (CSRF 쿠키가 아직 없음)
refresh:          Refresh 행 검증 후 위의 쿠키/헤더 일치 검사
```

CSRF 값은 인증 자격증명이 아니며 서버에는 원문도 해시도 저장하지 않는다. 로그아웃과 계정
삭제에서는 쿠키를 지운다. 새 로그인은 새 값을 덮어쓴다.

### 자동 검사

```
정상 토큰           → 성공
헤더 없음           → 403
헤더 ≠ 쿠키         → 403
JSON 아닌 상태 변경 → 415
교차 출처 signup/login → 403
GET                 → CSRF 검사 없음 (상태를 바꾸지 않는다)
```

**앞의 셋은 표본이 아니라 전수다**(`test_t07_csrf.py`). 앱의 라우팅 테이블에서 상태를
바꾸는 라우트를 뽑아 **11개 전부**에 세 시나리오를 돌린다. 한 엔드포인트에서만 확인하면,
CSRF 검사를 빠뜨린 다른 엔드포인트는 **읽어서는 안 보이고 물어봐야만 보인다.**
스윕이 조용히 0개를 매칭하는 경우도 건수 하한으로 막았다.

---

## 6. 무차별 대입 — DB 기반

**메모리에 셀 수 없다.** Render Free는 15분 뒤 잠들고 깨면서 재시작한다. `failed = {}`는
재시작마다 0이 되므로, 세는 척만 하는 코드가 된다. `login_attempts` 표에 적는다.

### 정책

```
창(window)     15분
임계           같은 (email, ip_hash) 실패 5회  또는  같은 ip_hash 실패 20회
잠금           60초, 이후 실패마다 배로 늘려 최대 15분
해제           로그인 성공 시 그 (email, ip_hash)의 실패 기록을 지운다
```

정확한 상태 전이는 이렇다.

- 임계에 닿은 실패의 `attempted_at`부터 잠금 시간을 잰다. 잠금 중 요청은 `LOGIN_BLOCKED`로
  남기되 실패 횟수에는 넣지 않는다. 그렇지 않으면 공격자가 요청만 계속 보내 피해자의 잠금을
  15분으로 붙들 수 있다.
- 잠금이 끝난 뒤 다시 틀린 비밀번호가 들어올 때 실패 단계가 하나 늘고 다음 잠금이 배증한다.
- 존재 여부를 조회하거나 Argon2를 돌리기 전에 같은 email/IP와 IP 전역 잠금을 먼저 계산한다.
  같은 입력 이력에는 존재하는 계정과 없는 계정이 같은 429 경로를 지난다.
- `login_attempts`에는 `succeeded`만으로 차단과 실패를 섞지 않고 `result` 열
  (`failure | blocked | success`)을 둔다. 배증 계산은 `failure`만 센다.

**5회·60초의 근거**: 사람이 비밀번호를 틀리는 횟수는 대체로 2~3회다. 5회는 정상 사용자를
거의 건드리지 않으면서, 첫 잠금 뒤 같은 email/IP의 시도를 최대 **5/60초 수준**으로 낮춘다.
배증을 두는 이유는 고정 60초면 공격자가 그냥 60초마다 5개씩 계속 시도하기 때문이다.
15분 상한은 정상 사용자가 영구히 잠기지 않게 하는 자리다.

### 계정 존재 여부를 알리지 않는 두 가지 장치

- **존재하지 않는 계정의 시도도 센다.** 안 세면 "잠기지 않는다 = 없는 계정"이 된다.
- **잠금 응답도 계정 존재와 무관하다.** 429와 그 문구가 두 경우 같다. 여기서 정직하게
  적을 교환: 잠긴 정상 사용자가 "잠겼다"는 것을 알 수 있어야 하는데, 그 안내가 곧 계정
  존재의 증거가 된다. **존재를 감추는 쪽을 골랐고**, 그래서 안내 문구가 불친절하다.
  이건 ⑥에 적는다.

고정 더미 해시는 운영 Argon2 매개변수와 같은 비용으로 만든다. 잠기지 않은 요청은 계정이
없어도 검증을 한 번 수행한다. 단 가입 중복 응답(C98) 자체가 계정 존재를 드러내므로, 여기서
말하는 목표는 C99의 로그인 경로를 더 빠른 별도 oracle로 만들지 않는 것이다.

IP는 원문을 저장하지 않는다 — `HMAC-SHA-256(IP_HASH_SECRET, canonical_ip)`. IP 주소는
후보 공간이 작아 공개 salt를 붙인 SHA-256이면 DB 유출 뒤 역대입할 수 있다. 별도 키는
Render가 만들고 JWT 서명 키와 공유하지 않는다. 이 키를 회전하면 과거 시도와 새 시도가
이어지지 않아 제한 창이 초기화된다는 대가를 운영 절차에 적는다.

**정리**: 24시간 지난 `login_attempts` 행은 지운다. 로그인 경로에서 확률적으로
(1/100) 청소해 별도 스케줄러 없이 끝낸다 — Free에는 크론이 없다.

---

## 7. 보안 이벤트 기록

T06에는 감사 로그가 없었고, 그것이 이전 설계의 ⑥ 항목이었다. 이번에는 만든다.

```
LOGIN_SUCCESS              LOGIN_FAILURE            LOGIN_BLOCKED
LOGOUT                     SESSION_REVOKED          SESSION_EXPIRED
REFRESH_TOKEN_ROTATED      REFRESH_TOKEN_REUSE_DETECTED
CSRF_REJECTED              AUTHORIZATION_DENIED
PASSWORD_CHANGED           SIGNUP_SUCCESS           SIGNUP_DUPLICATE
ACCOUNT_DELETED
```

### 절대 들어가면 안 되는 값

```
비밀번호 · 비밀번호 해시 · Access 토큰 원문 · Refresh 토큰 원문
CSRF 토큰 원문 · JWT_SECRET · Authorization 헤더 원문 · 원본 IP
```

**마스킹은 `app/security/redact.py`의 함수 하나에서만 한다.** 호출부마다 가리면 언젠가
한 곳을 빠뜨리고, 그게 곧 C115·C131 위반이다. `security_events`에 쓰는 경로와 증거
스크립트가 출력하는 경로가 **같은 함수를 지나게** 배치한다.

자동 검사: 이벤트를 남기는 모든 경로를 한 번씩 태우고, `security_events` 전체와 증거
파일 전체를 훑어 토큰 모양 문자열이 없는지 확인한다.

---

## 8. 화면

지금 앱은 라우터가 없는 한 화면짜리다. C03·C97을 보이려면 **주소가 갈려야 한다**.

- `react-router-dom` 도입
- `/login`, `/signup` — 로그인하지 않아도 열린다 (C03: 심사자가 계정 없이 여기까지는 봄)
- `/app` — 자료 화면. 로그인 안 했으면 **`/login`으로 보낸다** (C97)
- Flask에 SPA 폴백 라우트 추가: `/login`·`/signup`·`/app` 직접 접근 시 `index.html`
- `/` 는 `/app`으로 보내고, 관문이 다시 판단한다 — 로그인 안 했으면 `/login`,
  했으면 그대로. 리다이렉트 규칙을 두 군데 두지 않으려고 이렇게 했다

Flask 쪽 폴백은 **catch-all이 아니라 목록**이다(`SPA_ROUTES`). catch-all은 오타 난
`/api/plnas`에도 셸과 200을 돌려주고, 그러면 명확한 404가 빈 화면으로 바뀐다.
검사: `backend/tests/acceptance/test_t07_spa_routes.py`.

**Access 만료(10분)를 사용자가 느끼면 안 된다.** API가 401을 주면 프런트가 자동으로
`/api/auth/refresh`를 한 번 호출하고 원 요청을 재시도한다. 재시도도 401이면 그때
`/login`으로 보낸다. **재귀하지 않도록** refresh 자체의 401은 재시도 대상에서 뺀다.

여기에는 직렬화가 필수다. **구현은 설계가 나눠 놓았던 둘을 하나로 합쳤다.** 임계 구역을
`Web Lock` 안에 두고, 그 안에서 **원 요청을 먼저 다시 보낸다.** 다른 탭이든 같은 탭의
다른 요청이든 이미 갱신했으면 그 재시도가 200으로 돌아오고, refresh는 아예 일어나지 않는다.
따로 single-flight Promise를 둘 필요가 없어졌다 — 재확인이 그 일을 대신한다.
탭 안 순서는 module-level 큐가, 탭 사이는 Web Lock이 잡는다.
Web Locks가 없는 브라우저의 fallback은 BroadcastChannel로 진행 중 상태를 공유한다.
인증값은 어느 경우에도 storage나 메시지에 싣지 않는다.

자동 검사는 `frontend/src/api/http.test.ts`. 동시 401 5건에서 **refresh 1회**, 재확인
5회까지 개수로 못 박았고, 두 탭은 모듈 인스턴스 둘이 같은 Web Lock을 나눠 갖는 모양으로
재현한다. refresh 자신의 401을 재시도하지 않는 것도 여기서 본다.

회전 응답이 네트워크에서 유실된 뒤 옛 Refresh를 재시도하면 엄격한 재사용 탐지가 계열을
끊는다. B 원문을 DB에 저장하지 않는 현재 구조에서는 안전하게 같은 응답을 재전송할 수 없다.
이 경우 재로그인을 요구하는 것은 알고 남긴 제한이며 ⑥에 적는다.

T06 첫 화면의 **"지금은 로그인이 없어 링크를 아는 사람은 누구나 볼 수 있습니다" 문구를
지운다.** 더는 사실이 아니고, 남겨 두면 그 자체로 감점 사유다.

계정 화면(`/app` 안): 비밀번호 변경 · 내보내기 · **계정 삭제**(지워진다는 안내 문구 포함, C134).

토큰 원문은 **어떤 것도 `localStorage`·`sessionStorage`에 두지 않는다.** 프런트가 아는
것은 "로그인했는가"뿐이고, 그건 `GET /api/auth/me`가 답한다.

---

## 9. 5일 실사용과 규칙 변경 (카드 5)

이건 코드보다 **기록 구조**의 문제다. C09~C15는 "규칙 변경 기록이 2일차 뒤·3일차 앞에
놓이고, 1일차와 2일차 기록을 정확히 가리킬 것"을 요구한다.

```
plan_rule_changes
  id, plan_id, changed_at (timestamptz),
  reason (text), rule_before (text), rule_after (text)

plan_rule_change_citations
  rule_change_id fk on delete cascade,
  execution_id fk on delete restrict,
  day_number smallint check in (1, 2),
  primary key (rule_change_id, day_number),
  unique (rule_change_id, execution_id)
```

JSON ID 배열로 두지 않는다. FK가 없는 문자열은 삭제됐거나 다른 사용자의 실행 기록도 가리킬
수 있어 C12의 "정확히"를 DB가 지키지 못한다. 서비스는 인용 두 건이 같은 plan 소유이고
Asia/Seoul 날짜 순서가 1일차·2일차이며 `changed_at`이 두 기록 뒤인지 한 트랜잭션에서 검사한다.
3일차 기록은 이 변경 뒤에만 생성되도록 관찰 plan의 실행 생성 경로에서도 순서를 검사한다.

두 방향 다 구현했다. 규칙 변경 쪽은 3일차 기록이 이미 있으면 거부하고, 실행 생성 쪽은
`OBSERVATION_PLAN_ID` 계획에 한해 규칙 변경이 없는 동안 3일차 기록을 거부한다. 한 방향만
막으면 남은 방향으로 순서가 깨지고, **깨진 순서는 되돌릴 방법이 시각을 고치거나 5일을
다시 시작하는 것뿐이다.** 다른 계획은 이 규칙과 무관하다 — C100으로 넘어온 T06 기록까지
순서를 강요하면, 그 기록이 애초에 참여하지 않은 기준으로 사용자를 막는 셈이다.

인용은 JSON 배열이 아니라 표라고 위에 적었는데, `execution_id`의 삭제 동작은 RESTRICT가
아니라 **NO ACTION**으로 갔다. 둘 다 인용된 기록의 단독 삭제를 막지만, RESTRICT는 행이
사라지는 즉시 검사한다. C134의 계정 삭제는 plans→tasks→executions와
plans→rule_changes→citations 두 갈래로 동시에 내려가고 그 사이 순서가 정해져 있지 않아서,
RESTRICT면 계정 삭제가 갈래 순서에 따라 실패한다. NO ACTION은 문장 끝에 검사하므로 그때는
인용 행도 함께 사라져 있다.

`docs/T07-STUDY-PROTOCOL.md`에 1일차에 **한 번만** 고정할 것들을 적는다 —
질문 한 문장(C04) · 지표 하나(C05) · 단위(C06) · 계산 규칙(C08) · 결측(C23) ·
중복(C24) · 이상값(C25) · 반올림(C26) · 주 시작 요일(C27). **작성 완료.**

그 규칙들은 문서에만 있지 않다. 계산은 `app/services/metrics.py` **한 곳**에서만 하고,
프로토콜 문서의 표가 그 코드의 이름을 가리킨다. C13~C15가 "전후 비교에 같은 지표·단위·
계산"을 요구하는데, 두 번 조심해서 지키는 것보다 구현이 하나뿐인 편이 확실하다.
반올림은 `round()`가 아니라 `Decimal(ROUND_HALF_UP)`이다 — 파이썬 기본 반올림은 절반을
짝수로 보내서 `1.125 → 1.12`가 되고, **손계산과 어긋나는 지표는 C132의 검산을 통과할 수
없다.**

T06 이관 자료와 T07의 "정확히 5일"을 섞어 세지 않도록 **T07 관찰용 plan ID 하나**를
프로토콜에 고정한다. C07~C15와 C132의 쿼리·화면·증거는 모두 이 plan ID만 대상으로
하고, 시작 전에 그 계획의 기록 날짜가 0개임을 남긴다. T06 자료는 C100 때문에 같은 계정에
남지만 5일 관찰 집합에는 들어오지 않는다.

규칙 변경은 문서만 적는 일이 아니다. `plan_rule_changes`를 만들고 조회하는 API와 화면,
1·2일차 실행 기록 두 개를 고르는 UI가 **첫 실사용 배포에 포함**되어야 한다. 2일차 저녁에
기능이 없으면 3일차 전에 기준을 만족시킬 수 없고 5일 시계를 다시 시작해야 한다.

**지표 확정(2026-09-03)**: **하루 계획 대비 실제 비율** — 단위 `배`, 계산 `실제분 ÷ 예상분`,
소수 둘째 자리 반올림. T06에서 이미 게이지로 쓰던 축이라 5일 비교가 자연스럽다.
1일차에 한 번 고정하고 5일 내내 바꾸지 않는다(C05·C06·C08·C13~C15).

---

## 10. 증거 수집 구조 (④ · C129)

"막았습니다"가 아니라 장면이 필요하므로, 증거를 **손으로 캡처하지 않고 스크립트로
찍는다**. 손으로 모으면 비밀값을 가리는 것을 잊는다.

```
backend/scripts/collect_auth_evidence.py
  → 계정 두 개 생성 → 자료 넣기 → 양방향 읽기·수정·삭제 시도
  → 회전 · 재사용 · 로그아웃 재생 · CSRF · 잠금 · 만료
  → 거절 전후 건수 비교
  → docs/T07-EVIDENCE/*.md 로 출력, 전부 redact() 한 곳을 지난다
```

| 파일 | 담는 것 | 기준 |
| --- | --- | --- |
| `00-hash-bench-render.md` | 배포 인스턴스 해싱 비용 | 설명서 ② |
| `01-signup-login-logout.md` | 가입·로그인·로그아웃, 중복 가입 거절, 같은 문구 두 경우 | C94~C99 |
| `02-password-storage.md` | 저장된 해시 한 개, 같은 비밀번호 두 계정의 서로 다른 해시 | C101~C107 |
| `03-logout-replay-blocked.md` | 같은 주소·같은 방식 성공/거절 쌍 | C108~C110 · C114 |
| `04-refresh-rotation.md` | A 사용 → B 발급, A는 죽음 | C111 |
| `05-refresh-reuse-detected.md` | 재사용 → 계열 전체 폐기 | 설명서 ⑤ |
| `06-csrf-blocked.md` | 정상/헤더 없음/불일치/JSON 아님/교차 출처 로그인 | 설명서 ⑥ |
| `07-bruteforce-blocked.md` | 5회 실패 → 429, 없는 계정도 같은 응답 | 설명서 ⑤ |
| `08-cross-user-access-blocked.md` | 양방향 읽기·수정·삭제, 헤더·본문 위조, 미로그인, 목록, 건수 대조 | C116~C126 |
| `09-session-expiration.md` | 유휴 만료·절대 만료 | C111 |
| `10-security-events.md` | 남은 이벤트 목록, 원문 없음 확인 | C115 · C131 |
| `11-totals.md` | 화면 합계·평균과 손으로 더한 값 | C132 |

만료 두 개는 실제로 48시간·14일을 기다릴 수 없으므로, **시간을 주입 가능한 인자로 두고**
(`now` 를 서비스가 인자로 받는다) 테스트에서 앞당긴다. 그 사실을 증거 파일에 적는다 —
숨기면 그게 더 나쁘다. 이 시뮬레이션과 별도로 운영 설정이 실제로 48시간·14일이고 쿠키의
수명이 그보다 길게 열리지 않는다는 설정 검사를 붙인다.

C106의 "서버 로그·화면·네트워크 응답 어디에도"는 무한한 부재 증명이라고 쓰지 않는다.
가입·로그인·실패·잠금·회전·로그아웃·비밀번호 변경을 한 번씩 실행한 뒤 **그 실행에서
수집한** 응답, 브라우저 화면, Render 로그 구간과 `security_events` 전체를 스캔했다고 범위를
적는다. 여기에 공통 redact 함수의 단위 검사와 Git·빌드 스캔을 합친다.

---

## 11. ⑥ 아직 못 막은 것 (C130)

이전 초안에서 **줄어든 것**: 무차별 대입(6절), 감사 로그(7절), CSRF 토큰(5절)은 이제 있다.

남은 것:

- **IP를 갈아 가는 분산 공격** — 현재 잠금은 `(email, ip)`와 IP 기준이라, 매번 다른 IP에서
  같은 계정을 공격하거나 다른 계정을 한 번씩 훑으면 어느 카운터도 임계에 닿지 않는다.
  막으려면 계정 전역 제한, 전역 시도율 감시나 비밀번호 사전 대조가 필요하지만 그것들은
  공격자가 특정 계정을 잠그는 DoS와의 새 교환을 만든다.
- **비밀번호 재설정 없음** — 잊으면 복구 수단이 없다. 편의 문제이자, 급하게 붙이면
  거기가 가장 약한 고리가 되는 자리다.
- **두 번째 인증 수단 없음** — 비밀번호 하나가 새면 그걸로 끝이다.
- **이메일 소유 확인 없음** — 남의 이메일로 가입할 수 있다.
- **가입 화면이 계정 존재를 알린다** — 로그인은 C99대로 두 경우를 같은 문구로 막지만,
  **가입은 중복을 거절해야 하므로**(C98) "이미 가입된 이메일입니다"가 나간다. 주소를
  하나씩 넣어 보면 어느 것이 등록됐는지 알 수 있다. 로그인 쪽에서 막은 것을 가입 쪽에서
  여는 셈인데, 두 기준을 동시에 만족시킬 방법이 없어 **C98을 택했다.** 제대로 닫으려면
  가입도 항상 같은 응답을 주고 확인 메일로 갈라야 하는데, 그건 이메일 발송이 전제다.
- **잠금 안내가 불친절하다** — 계정 존재를 감추려고 429 문구를 같게 뒀다(6절). 정상
  사용자가 왜 막혔는지 알기 어렵다. 의도한 교환이다.
- **동시 refresh 두 건도 계열을 끊는다** — 구현하고 나서야 분명해진 것. 두 요청이 같은
  토큰으로 동시에 들어오면 진 쪽이 `rotated`를 보고, 서버 입장에서 그건 재생과 구별되지
  않는다. 이긴 쪽이 방금 받은 후계까지 폐기된다. 유예 창(grace window)을 두면 막을 수
  있지만, 그건 훔친 토큰에도 같은 유예를 주는 것이다. **프런트가 refresh를 직렬화하는
  이유가 이것**이고(8절), 직렬화가 뚫린 자리는 재로그인으로 갚는다.
- **회전 응답 유실은 정상 사용자도 끊는다** — 프런트의 단일/교차 탭 직렬화로 평상시 동시
  refresh는 막지만, 서버가 B를 commit한 뒤 응답이 유실되어 A가 재시도되면 재사용 탐지가
  계열 전체를 폐기한다. B 원문을 DB에 저장하지 않는 정책과 엄격 탐지를 유지하는 대가로
  재로그인을 요구한다.
- **Access 토큰 자체는 폐기 목록이 없다** — `sid`로 세션 행을 보므로 즉시 끊기지만,
  그건 세션 단위다. "이 Access 하나만 죽이기"는 못 한다. 필요한 장면이 아니라 안 만들었다.
- **XSS가 나면 CSRF 방어가 의미 없다** — 같은 출처의 스크립트는 CSRF 쿠키를 읽을 수 있다.
  기대는 CSP(`script-src 'self'`, T06에서 넣어 둠)에 걸려 있다.

---

## 12. 문서 배치

```
docs/source/T07-OFFICIAL-ASSIGNMENT.md        원문
docs/process/T07-AUTH-DIRECTION-2026-09-03.md 방향 결정
docs/T07-ARCHITECTURE.md                      이 문서
docs/T07-AUTH-OPTIONS.md                      판단 재료 (선택 전 상태 보존)
docs/T07-REQUIREMENTS.md                      원문을 구현 언어로 옮긴 것
docs/T07-ACCEPTANCE-MATRIX.md                 고정 확인 항목 → 자동 검사와 1:1
docs/T07-STUDY-PROTOCOL.md                    1일차에 고정하는 정의
docs/T07-AUTH-GUIDE.md                        제출물: 설명서 여섯 항목
docs/T07-EVIDENCE/                            스크립트가 찍는 요청·응답
docs/SUBMISSION.md                            제출 양식에 붙여 넣을 것
```

T06 문서는 그대로 둔다. 지우면 "이어 붙였다"(C100)의 근거가 사라진다.

---

## 13. 순서 — 두 단계로 자른다

**5일 기록이 일정에서 가장 빡빡한 제약이다.** 잠긴 앱으로 서로 다른 날짜 5일이 필요하고,
그 5일은 배포가 끝난 다음 날부터 센다. 고급 항목 때문에 배포가 밀리면 안 된다.

### 1단계 — 배포 전에 반드시 (5일 기록의 전제)

| # | 할 일 | 끝났다는 기준 |
| --- | --- | --- |
| 1 | 기존 코드·DB 분석, 새 표 + `plans.user_id` nullable + reflection FK 수정 | 기존 테스트 53개, PostgreSQL cascade 검사 통과 |
| 2 | Argon2id 비밀번호 서비스 (▢ 매개변수는 동시성·RSS 측정값) | 같은 비밀번호 두 해시가 다름 |
| 3 | 가입 · 로그인 (더미 검증, JSON·Origin 포함) | C94·C95·C98·C99 |
| 4 | Access JWT 발급·검증, `sid` 바인딩 가드 | 만료·폐기 세션 401, sub/user_id 일치 |
| 5 | 잠금 기반 Refresh 회전 | 동시 A 두 건에서 후계가 하나뿐 |
| 6 | 로그아웃 · 폐기와 Refresh 경합 | C109·C110·C114 |
| 7 | 단건·목록·집계·생성·export 사용자 범위 | C116~C126, A export에 B 자료 0 |
| 8 | `__Host-` 이중 제출 CSRF + JSON·Origin | 정상/없음/불일치/JSON 아님/교차 출처 |
| 9 | 프런트 라우팅 · 로그인/가입 · single-flight/교차 탭 refresh | **끝남** — vitest 19개, SPA 폴백 13개 |
| 10 | 규칙 변경 저장·조회·1·2일차 기록 선택 UI | **끝남** — C09~C15 검사 통과, 화면 확인 |
| 11 | T06 자료 claim 배포 | 고정 ID별 결과, 주인 없는 행 0 |
| 12 | 별도 마이그레이션으로 `user_id` NOT NULL | 재실행 후에도 주인 없는 행 0 |
| 13 | **기존 T06 Render 서비스·Neon에 배포** | `/api/live` 200, 첫 화면 로그인, 관찰 plan 날짜 0개 |

### 2단계 — 5일 기록과 나란히

14. Refresh 재사용 탐지 (계열 폐기) — **끝남**
15. 무차별 대입 잠금 — **끝남**
16. 유휴·절대 만료 — **끝남**
17. 비밀번호 변경 + 전 세션 폐기 경합 검사
18. 계정 삭제 + PostgreSQL cascade 검사
19. 보안 이벤트 기록 — **틀과 인증 경로 끝남**, 남은 경로는 15~18과 함께
20. 증거 스크립트 · `docs/T07-ACCEPTANCE-MATRIX.md`
21. 설명서 여섯 항목 · 확인 4줄 · 판단 3줄

5일 기록이 남기는 것은 **지정한 관찰 plan의 다이어리 사용 기록**이라, 3일차에 재사용
탐지가 붙어도 그 기록이 무효가 되지 않는다. 규칙 변경 기능은 이미 1단계에 있다. 배포할
때마다 재시작이 붙으므로 **규칙 변경을 기록하는 2일차 저녁 전후로는 배포하지 않는다.**

---

## 결정 현황 (2026-09-03)

| 항목 | 상태 |
| --- | --- |
| 관찰 지표 | **확정** — 하루 계획 대비 실제 비율(배) |
| 원격 저장소 | **확정** — `myeongjundev/t07-plando-see-diary` (public) |
| 비밀번호 보관 | **확정** — Argon2id / `argon2-cffi`. **매개변수만 측정 대기 ▢** |
| 세션 표현 | **확정** — Access JWT(10분, `sid` 바인딩) + 회전 불투명 Refresh |
| 세션 운반 | **확정** — 쿠키 세 개 (4절 표) |
| CSRF | **리뷰 반영 확정** — SameSite + JSON/Origin + `__Host-` 이중 제출. DB 세션 바인딩은 제거 |
| 무차별 대입 | **확정** — DB 기반. 5회/15분 → 60초 배증, 최대 15분 |
| 세션 만료 | **확정** — 유휴 48시간 + 절대 14일 |
| 보안 이벤트 기록 | **확정** — `security_events` 표 |
| 배포 | **확정** — T06 서비스·T06 Neon을 그대로 이어받는다. **T06 제출 후에** 저장소 연결을 돌린다 |
