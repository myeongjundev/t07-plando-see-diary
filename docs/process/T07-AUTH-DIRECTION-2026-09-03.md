# T07 인증 설계 확정 프롬프트

> 보존 문서: 이 파일은 사용자가 정한 하이브리드·Defense in Depth 방향의 원문이다.
> 2026-09-03 설계 리뷰에서 CSRF 세션 바인딩, 요청 순서, refresh 경합, 이관 순서와
> 1단계 범위가 보정됐다. 구현 시 최신 확정안은 `docs/T07-ARCHITECTURE.md`를 따른다.

T07 과제(플랜두씨 다이어리 2 — 인증)를 이어서 작업한다.

저장소:
https://github.com/myeongjundev/t07-plando-see-diary

먼저 아래 문서를 반드시 읽고 현재 구조와 기존 결정사항을 파악한다.

- `docs/process/T07-HANDOFF-2026-09-03.md`
- `docs/T07-ARCHITECTURE.md`
- `docs/T07-AUTH-OPTIONS.md`
- `docs/source/T07-OFFICIAL-ASSIGNMENT.md`

이번 T07은 단순히 가입/로그인이 동작하는 수준으로 끝내지 않는다.

SKT ALEPH 네트워크·보안 과정의 포트폴리오라는 점을 고려해, 인증 시스템 자체가 Defense in Depth 구조를 보여주도록 설계한다.

---

# 1. 최종 인증 방향

다음 조합을 우선안으로 채택한다.

## Password

- `Argon2id`
- Python 라이브러리: `argon2-cffi`
- 비밀번호 원문 저장 절대 금지
- Argon2 파라미터는 개발 PC 결과로 확정하지 않는다.
- 실제 Render Free 환경의 성능을 측정한 후 로그인 응답시간과 서버 자원 사이의 균형을 보고 결정한다.

목표:

```text
보안성이 충분하면서
실제 Render 환경에서 현실적인 latency를 유지하는
가장 높은 비용의 Argon2id 설정
```

---

# 2. JWT 구조

JWT를 단독 장기 세션으로 사용하지 않는다.

다음의 Hybrid Token Architecture를 사용한다.

```text
Access Token
+
Refresh Token
```

## Access Token

- JWT
- 짧은 수명
- 권장 TTL: 약 10~15분
- 서버가 서명을 검증하여 인증
- 필요한 최소 claim만 포함한다.

예:

```text
sub
iat
exp
jti
```

민감정보는 JWT payload에 넣지 않는다.

특히 다음은 금지:

```text
password
password hash
refresh token
secret
민감 개인정보
```

---

# 3. Refresh Token

Refresh Token은 JWT보다 `opaque random token`을 우선 사용한다.

생성 예:

```python
secrets.token_urlsafe(32)
```

브라우저에는 원문을 전달할 수 있지만 DB에는 절대로 원문을 저장하지 않는다.

DB 저장:

```text
SHA-256(refresh_token)
```

형태로 저장한다.

예상 테이블 구조:

```text
refresh_sessions

id
user_id
token_hash
family_id
created_at
last_used_at
expires_at
revoked_at
replaced_by_id
```

실제 프로젝트 구조에 맞춰 이름과 컬럼은 조정 가능하다.

---

# 4. Refresh Token Rotation

Refresh Token은 재사용 가능한 고정 토큰으로 운영하지 않는다.

반드시 Rotation을 적용한다.

정상 흐름:

```text
Refresh Token A
       ↓
refresh 요청
       ↓
A 검증
       ↓
A revoke
       ↓
Access JWT 새로 발급
       +
Refresh Token B 발급
```

즉 하나의 Refresh Token은 정상적으로 한 번만 사용된다.

---

# 5. Refresh Token Reuse Detection

ALEPH 보안 포트폴리오에서 중요한 기능이다.

이미 사용되었거나 revoke된 Refresh Token이 다시 사용되면 단순히 401만 반환하고 끝내지 않는다.

다음과 같은 공격 가능성을 고려한다.

```text
정상 사용자
Refresh A 사용
→ Refresh B 발급

공격자
탈취한 Refresh A 재사용
→ 이미 사용된 토큰임을 탐지
```

이 경우:

```text
REFRESH_TOKEN_REUSE_DETECTED
```

보안 이벤트를 남기고,

가능하다면 동일 `family_id`에 속한 Refresh Session 전체를 revoke한다.

결과:

```text
해당 로그인 세션 계열 전체 폐기
→ 재로그인 요구
```

이 동작은 자동 테스트와 증거 문서로 남긴다.

---

# 6. Token Transport

JWT 또는 Refresh Token을 `localStorage`에 저장하지 않는다.

브라우저 인증값은 기본적으로 쿠키로 운반한다.

권장:

```text
HttpOnly
Secure
SameSite=Lax
Path=/
```

가능하다면 `__Host-` prefix 사용 가능 여부도 검토한다.

예:

```text
__Host-access
__Host-refresh
```

단 실제 배포 구조와 쿠키 path 요구사항을 보고 결정한다.

JavaScript에서 인증 토큰 원문을 읽지 못하도록 한다.

---

# 7. CSRF Defense

쿠키 기반 인증을 사용하므로 CSRF를 명시적으로 다룬다.

다음의 다층 방어를 사용한다.

```text
SameSite cookie
+
JSON-only state-changing request
+
CSRF token
```

CSRF 구현은 아래 둘 중 프로젝트 구조에 가장 적합한 방식을 선택한다.

```text
Double Submit Cookie
```

또는

```text
Session-bound CSRF Token
```

상태 변경 API:

```text
POST
PUT
PATCH
DELETE
```

등은 CSRF token 검증 없이 수행되지 않아야 한다.

자동 테스트:

```text
정상 token
→ 성공

CSRF token 없음
→ 403

잘못된 CSRF token
→ 403
```

---

# 8. Brute-force 대응

로그인 무차별 대입 방어를 구현한다.

Render Free는 프로세스 재시작 시 메모리가 사라질 수 있으므로 다음 방식은 금지한다.

```python
failed_attempts = {}
```

또는 기타 프로세스 메모리 기반 rate limiter.

DB 기반으로 구현한다.

권장 방식:

```text
login_attempts
```

테이블 또는 이에 준하는 영속 구조.

최소한 다음을 검토한다.

```text
계정 기준 반복 실패
IP 기준 반복 실패
일정 시간 내 실패 횟수
임시 lock
```

예시 정책:

```text
5회 연속 실패
→ 60초 잠금
```

정확한 숫자는 문서에 근거를 남긴다.

로그인 성공 시 필요한 실패 상태를 적절히 초기화한다.

존재하지 않는 계정에 대해서도 지나치게 빠른 실패 응답으로 계정 존재 여부가 노출되지 않도록 timing 차이를 고려한다.

---

# 9. Session Expiration

두 가지 만료를 적용한다.

```text
Idle Timeout
+
Absolute Timeout
```

초기 제안:

```text
Idle Timeout: 48시간
Absolute Lifetime: 14일
```

정확한 값은 기존 과제 요구사항과 UX를 보고 최종 확정한다.

의미:

```text
48시간 미사용
→ 재로그인

계속 사용하더라도 발급 후 14일
→ 반드시 재로그인
```

Refresh Session에 다음과 같은 상태가 필요할 수 있다.

```text
created_at
last_used_at
expires_at
```

매 API 요청마다 DB write가 과도하게 발생하지 않도록 `last_used_at` 갱신 전략도 고려한다.

예:

```text
10분 이상 차이가 날 때만 갱신
```

단 복잡도를 불필요하게 높이지 않는다.

---

# 10. Logout

로그아웃은 단순히 브라우저 쿠키만 삭제하고 끝내지 않는다.

반드시 서버 측 Refresh Session도 revoke한다.

```text
POST /logout
       ↓
DB refresh session revoke
       ↓
cookie expire/delete
```

로그아웃 후 이전 Refresh Token을 다시 사용했을 때:

```text
401 또는 명확한 인증 실패
```

가 발생해야 한다.

이 장면을 T07의 핵심 인증 증거로 남긴다.

---

# 11. Password Change

비밀번호 변경 시 보안 정책:

```text
기존 비밀번호 확인
       ↓
새 비밀번호 Argon2id hash
       ↓
users 업데이트
       ↓
기존 Refresh Session 전체 revoke
       ↓
재로그인
```

즉 비밀번호가 변경되면 기존 로그인 상태가 계속 살아 있지 않도록 한다.

---

# 12. Authorization

Authentication과 Authorization을 구분한다.

로그인이 되어 있다고 해서 다른 사용자의 다이어리 데이터를 읽거나 수정할 수 있어서는 안 된다.

모든 사용자 자원은 반드시 `user_id` 기준으로 검증한다.

예:

```text
GET /diary/123
```

에서 단순히 ID만 조회하지 않는다.

```text
resource.id = 123
AND
resource.user_id = current_user.id
```

조건을 만족해야 한다.

다른 사용자의 ID를 추측하여 요청하면:

```text
403
또는
404
```

프로젝트 정책에 따라 일관되게 처리한다.

이를 자동 테스트한다.

---

# 13. Security Event Logging

인증 관련 보안 이벤트를 구조적으로 기록한다.

예:

```text
LOGIN_SUCCESS
LOGIN_FAILURE
LOGIN_BLOCKED
LOGOUT
ACCESS_TOKEN_EXPIRED
REFRESH_TOKEN_ROTATED
REFRESH_TOKEN_REUSE_DETECTED
SESSION_REVOKED
PASSWORD_CHANGED
CSRF_REJECTED
AUTHORIZATION_DENIED
```

가능하다면 별도 테이블:

```text
security_events
```

를 사용한다.

예상 필드:

```text
id
user_id nullable
event_type
result
ip_hash nullable
created_at
metadata
```

단 다음 값은 로그에 절대 저장하면 안 된다.

```text
password
password hash
access token 원문
refresh token 원문
CSRF token 원문
SECRET_KEY
Authorization 헤더 원문
```

마스킹은 여러 곳에서 임의로 하지 말고 공통 출력/로깅 계층에서 일관되게 수행한다.

---

# 14. Render Free Hash Benchmark

현재 노트북 benchmark는 참고값일 뿐 최종 근거가 아니다.

배포 환경에서 다시 측정한다.

기존 스크립트:

```bash
python backend/scripts/bench_password_hashing.py --repeats 3 \
  --markdown docs/T07-EVIDENCE/00-hash-bench-render.md
```

Render Free에서 직접 Shell 실행이 가능한지 먼저 확인한다.

Shell이 지원되지 않는 환경이면 대체 방식을 설계한다.

예:

```text
일회성 startup benchmark
환경변수 BENCH_HASH=1
Render Logs 출력
```

또는 보안상 외부 공개되지 않는 일회성 검증 방식.

벤치마크용 엔드포인트를 외부에 영구 노출하면 안 된다.

측정 완료 후 관련 우회 코드/환경변수는 제거 또는 비활성화한다.

최종 결과는:

```text
docs/T07-EVIDENCE/00-hash-bench-render.md
```

에 남긴다.

---

# 15. Acceptance / Evidence

`docs/T07-ACCEPTANCE-MATRIX.md`를 작성한다.

각 보안 요구사항과 자동 테스트/증거를 1:1 대응시킨다.

예:

```text
Password hashing
↔ test_password_not_plaintext

Login
↔ test_login_success

Wrong password
↔ test_login_failure

CSRF
↔ test_csrf_missing_rejected

Logout replay
↔ test_revoked_refresh_rejected

Refresh rotation
↔ test_refresh_rotation

Refresh reuse
↔ test_refresh_reuse_revokes_family

Brute force
↔ test_login_lockout

Cross-user access
↔ test_other_user_diary_denied

Session expiration
↔ test_idle_expiry
↔ test_absolute_expiry
```

테스트 이름은 실제 코드에 맞춰 조정한다.

---

# 16. Evidence 디렉터리

가능하면 아래처럼 정리한다.

```text
docs/T07-EVIDENCE/

00-hash-bench-render.md
01-password-storage.md
02-login-cookie.md
03-logout-replay-blocked.md
04-refresh-rotation.md
05-refresh-reuse-detected.md
06-csrf-blocked.md
07-bruteforce-blocked.md
08-cross-user-access-blocked.md
09-session-expiration.md
10-security-events.md
```

증거 파일에는 실제 비밀번호/토큰/비밀키 원문을 절대 포함하지 않는다.

필요한 값은 마스킹한다.

---

# 17. 보안 설계의 핵심 설명

이 T07은 최종적으로 아래의 Defense in Depth 구조가 설명되어야 한다.

```text
Password DB leak
→ Argon2id

Access token theft
→ 짧은 JWT TTL

Refresh DB leak
→ SHA-256 token hash

XSS token extraction
→ HttpOnly cookie

CSRF
→ SameSite + JSON + CSRF token

Credential brute force
→ DB-based throttling / lockout

Stolen refresh token
→ Rotation + Reuse Detection

Logged-out token replay
→ Server-side revocation

Idle stolen session
→ Idle timeout

Long-lived stolen session
→ Absolute timeout

Cross-user ID guessing
→ Ownership authorization

Security incident analysis
→ Structured security event logging
```

---

# 18. 구현 우선순위

기존 `docs/T07-ARCHITECTURE.md` 10절의 순서를 최대한 존중하되, 인증 설계를 다음 순서로 구현한다.

```text
1. 기존 코드/DB 분석
2. users schema 및 migration
3. Argon2id password service
4. 회원가입
5. 로그인
6. Access JWT 발급/검증
7. Refresh Session DB 구조
8. Refresh Rotation
9. Logout / Revocation
10. Authorization Guard
11. CSRF
12. Brute-force protection
13. Idle / Absolute expiry
14. Password change + session revoke
15. Security Event Logging
16. Frontend 인증 상태 연결
17. 자동 테스트
18. Acceptance Matrix
19. Render 배포
20. 실제 배포 환경 검증
21. 5일 실사용 시작
```

---

# 19. 중요 일정 제약

과제에서 실제 서로 다른 날짜 5일의 사용 기록이 필요하다.

따라서 인증 구조가 완성되고 배포가 안정화되면 가능한 한 빨리 잠긴 앱으로 실사용을 시작한다.

고급 보안 기능 때문에 기본 로그인/배포 자체가 장기간 지연되지 않도록 한다.

기능은 단계적으로 추가할 수 있지만:

```text
회원가입
로그인
사용자 데이터 격리
로그아웃
배포
```

는 먼저 안정적으로 완성되어야 한다.

---

# 20. 하지 말아야 할 것

다음은 금지한다.

```text
비밀번호 평문 저장
비밀번호 로그 출력
JWT/Refresh Token 원문 DB 저장
Refresh Token localStorage 저장
Access Token 장기 수명
JWT에 민감정보 삽입
메모리 전용 brute-force counter
로그아웃 시 cookie만 삭제하고 DB revoke 안 함
다른 사용자의 resource ownership 검사 생략
보안 테스트 없이 "막았다"고 문서만 작성
```

---

# 최종 목표

이번 T07을 단순한 Flask 로그인 예제가 아니라 다음과 같이 설명할 수 있는 결과물로 만든다.

> T06 Plan-Do-See Diary에 인증·인가를 추가하면서 Argon2id 비밀번호 해싱, 짧은 수명의 JWT Access Token, PostgreSQL 기반 Rotating Refresh Token, Token Reuse Detection, CSRF 방어, 영속적인 로그인 공격 제한, 세션 만료 및 폐기, 사용자별 자원 격리, 구조화된 보안 이벤트 로깅을 적용한 Defense-in-Depth 인증 시스템을 설계하고 구현했다.

구현하기 전에 현재 문서와 코드를 분석하고, 이미 존재하는 구조를 불필요하게 대규모 재작성하지 않는다.

보안 기능 하나를 추가할 때마다 반드시 다음 세 가지를 함께 남긴다.

```text
왜 필요한가
어떻게 막는가
실제로 막혔다는 자동 테스트/증거
```

이 원칙을 이번 T07 전체 작업의 최우선 기준으로 삼는다.
