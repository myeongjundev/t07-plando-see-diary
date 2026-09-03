# T07 설계 — 잠금 구조

상태: **인증 조합 확정(2026-09-03). ▢ 표시 한 곳만 측정 대기 — Argon2id 매개변수.**

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

**배포도 T06과 갈라 놓는다.** 서비스도 데이터베이스도 새로 만든다.

- T06은 이미 `t06-plando-see-diary.onrender.com`으로 제출됐고, T06 기준은 그 첫 화면이
  **로그인 없이** 열릴 것을 요구한다. T07-C03은 자기 주소가 **로그인 화면으로** 열릴 것을
  요구한다. 한 서비스가 둘 다일 수 없다.
- T07 마이그레이션은 `plans.user_id`를 NOT NULL로 조인다. 같은 데이터베이스를 물리면
  **라이브 T06 앱이 깨진다.** T06 자료는 덤프·복원으로 새 Neon에 옮긴 뒤 이관한다(C100).

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
- 상한을 누르는 것: 512MB 인스턴스. `p=1`이라 동시 로그인 두 건이면 선언 메모리의 두 배.
  `m`을 47MiB로 올리면 두 건에 94MiB — 여유는 있지만 공짜는 아니다.
- 결과는 `docs/T07-EVIDENCE/00-hash-bench-render.md`, 확정값은 이 표에 채운다.

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
  csrf_sha256     char(64) not null              -- 세션에 묶인 CSRF 토큰 (5절)
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
  ip_hash           char(64) not null -- SHA-256(ip + 서버 소금). 원본 IP는 저장하지 않는다
  succeeded         boolean not null
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
유휴 만료에 충분하다.**

**`security_events.user_id`가 `on delete set null`인 이유**: C134가 계정과 자료를 함께
지우라고 한다. 사건 기록까지 지우면 "털린 뒤에 알아낼 방법"이 사라지고, 남겨 두면 지운
계정의 흔적이 남는다. 사람을 가리키는 열만 끊고 사건은 남기는 것이 두 요구를 다 지킨다.

**잠금 표를 따로 두지 않는 이유**: 잠금은 `login_attempts`의 최근 실패 건수에서 **파생**한다.
상태를 두 곳에 두면 어긋나는 날이 오고, 그때 어느 쪽이 참인지 코드가 답할 수 없다.

### 기존 표에 붙는 것

`plans.user_id`(FK, NOT NULL)를 **소유권의 유일한 뿌리**로 둔다. tasks·executions·
reflections·plan_revisions는 `user_id`를 따로 갖지 않고 **plans를 거쳐 주인을 판정**한다.

> 비정규화(각 표에 user_id 복사)를 하지 않는 이유: 두 곳에 적힌 주인이 어긋나는 순간
> 어느 쪽이 참인지 코드가 답할 수 없다. 조인 한 번이 그 위험보다 싸다.

### T06 자료를 내 계정으로 옮기기 (C100)

세 단계 이관으로, 중간에 주인 없는 행이 생기지 않게 한다.

1. `user_id`를 **nullable로 추가**
2. `backend/scripts/claim_t06_data.py` — 환경변수로 받은 이메일·비밀번호로 계정을
   만들고, `UPDATE plans SET user_id = :id WHERE user_id IS NULL` 실행
3. 다음 마이그레이션에서 **NOT NULL로 조인다**

셸이 없으므로 이 스크립트도 `BOOT_TASK`로 태워 보낸다. **비밀번호는 `BOOT_TASK_ARGS`가
아니라 별도 환경변수(`sync: false`)로 받는다** — `render.yaml`은 커밋되는 파일이고, 인자로
넘기면 로그의 명령줄에도 남는다.

옮기지 않을 것: T06 공개 앱에 남은 `프로젝트 테스트` 계획과 `<script>` 문자열이 든
삭제 완료 상태의 할 일. 스크립트가 무엇을 옮기고 무엇을 버렸는지 건수로 출력한다.

---

## 3. 요청이 지나는 길 (설명서 ③의 뼈대 · C128)

```
요청
 └ app/auth/csrf.py : @csrf_protect          (상태를 바꾸는 메서드에만)
      헤더 X-CSRF-Token 없음                          → 403
      헤더 ≠ __Host-pds_csrf 쿠키                     → 403
      SHA-256(헤더) ≠ refresh_sessions.csrf_sha256    → 403
 └ app/auth/guards.py : @login_required
      __Host-pds_access 쿠키 → JWT 서명·exp 검증      → 실패 401
      sid로 refresh_sessions 조회
        없음 / revoked_at 있음                        → 401
        expires_at 지남 (절대 14일)                   → 401
        last_used_at + 48시간 지남 (유휴)             → 401
      통과하면 g.current_user · g.session 을 채운다
 └ app/services/ownership.py : owned_plan(id) / owned_task(id) / owned_reflection(id)
      select(...).join(Plan).where(Plan.user_id == g.current_user.id)
      한 건이라도 못 찾으면 → 404 (있는데 남의 것 / 아예 없음을 구별해 주지 않는다)
 └ 기존 서비스 계층 (T06 그대로)
```

거절을 만드는 자리는 **이 세 파일뿐이다.** C126에서 "거절을 만들어 내는 소스 위치"로
가리킬 곳이 한 군데로 모이도록 일부러 이렇게 나눈다. API 함수 안에서 각자 주인을
확인하게 두면, 나중에 한 곳을 빠뜨렸을 때 그것을 찾을 방법이 없다.

`@csrf_protect`가 `@login_required`보다 **앞**인 이유: CSRF는 "이 요청이 우리 화면에서
왔는가"를 묻는 것이라 신원 확인보다 먼저 답해야 한다. 뒤에 두면 로그인 상태에서만 CSRF를
검사하게 되어, 검사 자체가 로그인 여부를 알리는 신호가 된다.

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

기존 T06 엔드포인트 22개는 주소를 바꾸지 않는다. `@login_required` + `owned_*` 두 줄만
앞에 붙는다. 주소가 그대로여야 "T06에서는 열리던 것이 T07에서는 401"이라는 장면이
같은 주소로 찍힌다.

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

**접두사 판단.** `__Host-`는 `Path=/`를 강제하므로 refresh 쿠키에는 쓸 수 없다 — 경로를
좁히는 쪽이 더 값어치 있다고 보고 `__Secure-`를 골랐다. 접두사가 원래 막는 위협은
형제 서브도메인의 쿠키 덮어쓰기인데, **`onrender.com`은 Public Suffix List에 등재돼
있어**(2026-09-03 확인, PSL 15408행) 브라우저가 `Domain=.onrender.com` 쿠키를 아예
거부한다. 즉 이 호스트에서는 접두사가 결정적이지 않다. 그래도 붙이는 이유는 나중에
자체 도메인으로 옮겼을 때 조용히 약해지지 않게 하기 위해서다.

### 비밀키 (C113)

T06에는 비밀키가 하나도 없었다. JWT를 넣으면서 `JWT_SECRET`이 생기므로, **없음을
증명해야 하는 대상이 생겼다.** 이게 하이브리드의 두 번째 대가다.

- `render.yaml`에서 `generateValue: true` — **Render가 만든다.** 값이 git에도, 내
  기계에도, 이 대화에도 존재한 적이 없다.
- 프런트 번들에 들어갈 경로가 없다: 서명·검증은 전부 서버에서만 일어난다.
- `backend/scripts/audit_secrets.py`에 JWT 모양(`eyJ`로 시작하는 3토막)과 쿠키 이름
  패턴을 추가해 빌드 산출물·문서·git 이력을 계속 훑는다.
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

## 5. CSRF — 세 겹

쿠키 인증이라 교차 사이트 요청이 붙을 수 있다. 상태를 바꾸는 메서드
(`POST`·`PUT`·`PATCH`·`DELETE`)는 세 겹을 전부 통과해야 한다.

1. **`SameSite`** — 남의 사이트의 폼 POST가 쿠키를 달고 가지 못한다.
2. **`Content-Type: application/json` 요구** — 브라우저가 교차 출처로 이 헤더를 붙이려면
   프리플라이트를 거쳐야 하고, CORS를 열지 않았으므로 막힌다.
3. **세션에 묶인 이중 제출 토큰** — 아래.

### 왜 이중 제출만으로 끝내지 않고 세션에 묶는가

순수 이중 제출(쿠키 값 == 헤더 값)은 **공격자가 쿠키를 심을 수 있으면 뚫린다.** 자기가
아는 값을 쿠키와 헤더 양쪽에 넣으면 두 값이 일치하기 때문이다. 그래서 서버가 그 값을
**세션 행과 대조**한다:

```
로그인·회전 시:  csrf = secrets.token_urlsafe(32)
                 refresh_sessions.csrf_sha256 = SHA-256(csrf)
                 Set-Cookie: __Host-pds_csrf=csrf   (HttpOnly 아님)

요청 시:         X-CSRF-Token 헤더 == __Host-pds_csrf 쿠키   (이중 제출)
             AND SHA-256(헤더) == refresh_sessions[sid].csrf_sha256   (세션 바인딩)
```

공격자가 심은 값은 세션 행에 없으므로 셋째 검사에서 걸린다. **CSRF 토큰도 원문을 저장하지
않는다** — 비밀번호·refresh와 같은 논리다.

CSRF 토큰은 회전할 때마다 같이 갈린다. 수명이 refresh 세션과 정확히 같다.

### 자동 검사

```
정상 토큰           → 성공
헤더 없음           → 403
헤더 ≠ 쿠키         → 403
헤더 = 쿠키, 세션에 없는 값 → 403     ← 순수 이중 제출이라면 통과했을 것
GET                 → CSRF 검사 없음 (상태를 바꾸지 않는다)
```

넷째 줄이 이 설계에서 가장 설명 가치가 큰 검사다.

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

**5회·60초의 근거**: 사람이 비밀번호를 틀리는 횟수는 대체로 2~3회다. 5회는 정상 사용자를
거의 건드리지 않으면서, 잠금이 붙는 순간 공격자의 초당 시도를 **1/60 이하로** 떨어뜨린다.
배증을 두는 이유는 고정 60초면 공격자가 그냥 60초마다 5개씩 계속 시도하기 때문이다.
15분 상한은 정상 사용자가 영구히 잠기지 않게 하는 자리다.

### 계정 존재 여부를 알리지 않는 두 가지 장치

- **존재하지 않는 계정의 시도도 센다.** 안 세면 "잠기지 않는다 = 없는 계정"이 된다.
- **잠금 응답도 계정 존재와 무관하다.** 429와 그 문구가 두 경우 같다. 여기서 정직하게
  적을 교환: 잠긴 정상 사용자가 "잠겼다"는 것을 알 수 있어야 하는데, 그 안내가 곧 계정
  존재의 증거가 된다. **존재를 감추는 쪽을 골랐고**, 그래서 안내 문구가 불친절하다.
  이건 ⑥에 적는다.

IP는 원문을 저장하지 않는다 — `SHA-256(ip + 서버 소금)`. 같은 IP를 알아보는 데는
충분하고, DB가 새도 방문자 목록이 되지 않는다.

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
- `/` 는 `/login`으로 (로그인 상태면 `/app`)

**Access 만료(10분)를 사용자가 느끼면 안 된다.** API가 401을 주면 프런트가 자동으로
`/api/auth/refresh`를 한 번 호출하고 원 요청을 재시도한다. 재시도도 401이면 그때
`/login`으로 보낸다. **재귀하지 않도록** refresh 자체의 401은 재시도 대상에서 뺀다.

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
  reason (text), rule_before (text), rule_after (text),
  cited_execution_ids (json)   -- 1일차·2일차 기록의 ID를 정확히 가리킨다 (C12)
```

`docs/T07-STUDY-PROTOCOL.md`에 1일차에 **한 번만** 고정할 것들을 적는다 —
질문 한 문장(C04) · 지표 하나(C05) · 단위(C06) · 계산 규칙(C08) · 결측(C23) ·
중복(C24) · 이상값(C25) · 반올림(C26) · 주 시작 요일(C27).

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
| `06-csrf-blocked.md` | 정상/없음/불일치/세션에 없는 값 네 가지 | 설명서 ⑥ |
| `07-bruteforce-blocked.md` | 5회 실패 → 429, 없는 계정도 같은 응답 | 설명서 ⑤ |
| `08-cross-user-access-blocked.md` | 양방향 읽기·수정·삭제, 헤더·본문 위조, 미로그인, 목록, 건수 대조 | C116~C126 |
| `09-session-expiration.md` | 유휴 만료·절대 만료 | C111 |
| `10-security-events.md` | 남은 이벤트 목록, 원문 없음 확인 | C115 · C131 |
| `11-totals.md` | 화면 합계·평균과 손으로 더한 값 | C132 |

만료 두 개는 실제로 48시간·14일을 기다릴 수 없으므로, **시간을 주입 가능한 인자로 두고**
(`now` 를 서비스가 인자로 받는다) 테스트에서 앞당긴다. 그 사실을 증거 파일에 적는다 —
숨기면 그게 더 나쁘다.

---

## 11. ⑥ 아직 못 막은 것 (C130)

이전 초안에서 **줄어든 것**: 무차별 대입(6절), 감사 로그(7절), CSRF 토큰(5절)은 이제 있다.

남은 것:

- **IP를 갈아 가며 여러 계정을 훑는 공격** — 계정별·IP별 제한을 둬도, 매번 다른 IP에서
  다른 계정을 한 번씩 시도하면 어느 카운터도 임계에 닿지 않는다. 흔한 비밀번호를 쓴
  계정이 열린다. 막으려면 전역 시도율 감시나 비밀번호 사전 대조가 필요하다.
- **비밀번호 재설정 없음** — 잊으면 복구 수단이 없다. 편의 문제이자, 급하게 붙이면
  거기가 가장 약한 고리가 되는 자리다.
- **두 번째 인증 수단 없음** — 비밀번호 하나가 새면 그걸로 끝이다.
- **이메일 소유 확인 없음** — 남의 이메일로 가입할 수 있다.
- **잠금 안내가 불친절하다** — 계정 존재를 감추려고 429 문구를 같게 뒀다(6절). 정상
  사용자가 왜 막혔는지 알기 어렵다. 의도한 교환이다.
- **재사용 탐지가 정상 사용자도 끊는다** — 계열 전체를 폐기하므로, 네트워크 재시도 같은
  양성 오탐이 재로그인을 부를 수 있다. 탐지를 느슨하게 하는 것보다 낫다고 판단했다.
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
| 1 | 기존 코드·DB 분석, 마이그레이션 네 표 + `plans.user_id` nullable | 기존 테스트 53개 통과 |
| 2 | Argon2id 비밀번호 서비스 (▢ 매개변수는 측정값) | 같은 비밀번호 두 해시가 다름 |
| 3 | 가입 · 로그인 (더미 검증 포함) | C94·C95·C98·C99 |
| 4 | Access JWT 발급·검증, `sid` 바인딩 가드 | 만료된 토큰 401 |
| 5 | `refresh_sessions` + 회전 | A→B, A 죽음 |
| 6 | 로그아웃 · 폐기 | C109·C110·C114 |
| 7 | `owned_*` 소유권 가드, 기존 22개에 두 줄 | C116~C126 |
| 8 | CSRF 세 겹 | 4가지 검사 |
| 9 | T06 자료 이관 → `user_id` NOT NULL | 주인 없는 행 0 |
| 10 | 프런트 라우팅 · 로그인/가입/계정 화면 · 자동 refresh | C03·C97 |
| 11 | **배포** (새 서비스 + 새 Neon) | 첫 화면이 로그인 화면 |

### 2단계 — 5일 기록과 나란히

12. Refresh 재사용 탐지 (계열 폐기)
13. 무차별 대입 잠금
14. 유휴·절대 만료
15. 비밀번호 변경 + 전 세션 폐기
16. 보안 이벤트 기록
17. 증거 스크립트 · `docs/T07-ACCEPTANCE-MATRIX.md`
18. 설명서 여섯 항목 · 확인 4줄 · 판단 3줄

5일 기록이 남기는 것은 **다이어리 사용 기록**이라, 3일차에 재사용 탐지가 붙어도 그
기록이 무효가 되지 않는다. 다만 배포할 때마다 재시작이 붙으므로, **규칙 변경을 기록하는
2일차 저녁 전후로는 배포하지 않는다.**

---

## 결정 현황 (2026-09-03)

| 항목 | 상태 |
| --- | --- |
| 관찰 지표 | **확정** — 하루 계획 대비 실제 비율(배) |
| 원격 저장소 | **확정** — `myeongjundev/t07-plando-see-diary` (public) |
| 비밀번호 보관 | **확정** — Argon2id / `argon2-cffi`. **매개변수만 측정 대기 ▢** |
| 세션 표현 | **확정** — Access JWT(10분, `sid` 바인딩) + 회전 불투명 Refresh |
| 세션 운반 | **확정** — 쿠키 세 개 (4절 표) |
| CSRF | **확정** — 세 겹, 세션에 묶인 이중 제출 |
| 무차별 대입 | **확정** — DB 기반. 5회/15분 → 60초 배증, 최대 15분 |
| 세션 만료 | **확정** — 유휴 48시간 + 절대 14일 |
| 보안 이벤트 기록 | **확정** — `security_events` 표 |
| 배포 | **미결** — Render 새 서비스·새 Neon 생성 대기 |
