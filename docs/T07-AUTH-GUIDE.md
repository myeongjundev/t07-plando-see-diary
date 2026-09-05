# T07 인증 구현 설명서

2026-09-05 로컬 구현 기준. 운영 배포, 운영 해싱 벤치마크, 5일 실사용 검증은 아직
완료되지 않았다. 아래 요청·응답은 합성 계정으로 실행한 로컬 증거이며 실제 일기 기록이 아니다.
제출 전 남은 항목은 [제출 준비](T07-SUBMISSION.md)에 적는다.

이어 사용한 최종 T06 commit: `4f3ed709d75c573beac7fc95e700c7719b53087c`.
T06 제출 태그로 확인한 값이며 T07 HEAD의 조상이다.

## ① 무엇으로 붙였나

인증 흐름과 서버 세션 관리는 직접 구현했다. 비밀번호 해싱·검증은 **argon2-cffi의
Argon2id**, Access JWT 서명·검증은 **PyJWT**에 맡겼다. 인증 서비스는 사용하지 않는다.
Flask API와 React 화면을 한 출처에서 제공하고 PostgreSQL에 사용자·세션·소유권을 저장한다.
Google OAuth2는 목표 설계에만 있으며 현재 구현에는 없다.

다음은 2026-09-05 로컬 가상환경에서 확인한 버전이다. 운영 이미지의 설치 버전은 배포 후
별도로 확인해야 한다. `backend/pyproject.toml`은 범위 지정이므로 빌드 시 달라질 수 있다.

| 라이브러리 | 확인 버전 | 맡긴 역할 |
| --- | --- | --- |
| argon2-cffi | 25.1.0 | 비밀번호 해싱·검증 |
| PyJWT | 2.13.0 | Access JWT 서명·검증 |
| Flask | 3.1.3 | HTTP API |
| Flask-SQLAlchemy | 3.1.1 | Flask와 ORM 연결 |
| SQLAlchemy | 2.0.52 | 조회·트랜잭션·행 잠금 |
| Flask-Migrate | 4.1.0 | 마이그레이션 실행 |
| alembic | 1.19.1 | 스키마 변경 이력 |
| psycopg | 3.3.5 | PostgreSQL 연결 |
| waitress | 3.0.2 | 운영 WSGI 서버 |

## ② 왜 그걸 골랐나

Argon2id는 비밀번호 추측마다 메모리 비용을 요구하고 라이브러리가 난수 salt와 매개변수를
저장 문자열에 함께 넣는다. 같은 비밀번호의 두 저장 값이 달라지는 것을 직접 확인할 수 있다.
현재 기본값은 메모리 **19,456 KiB**, 반복 **2**, 병렬도 **1**이다.
[저장 모습과 서로 다른 두 해시의 확인 결과](T07-EVIDENCE/02-password-storage.md)를 남겼다.
salt·해시 원문은 가렸다. [로컬 측정](T07-EVIDENCE/00-hash-bench-local.md)은 참고이며,
[Render 측정 절차](T07-EVIDENCE/00-hash-bench-render-runbook.md)의 운영 결과는 아직 없다.
운영 로그인 지연이 목표 안에 든다고 주장하지 않는다.

로그인 상태는 **Access JWT + PostgreSQL의 Refresh Session 행**으로 알아본다.
Access의 `sid`가 살아 있는 세션을 가리키고 `sub`가 그 소유자와 일치해야 한다.
서명이 유효해도 로그아웃한 세션이면 거절한다. Access 수명은 **10분**, 세션은 **48시간
유휴 만료**, 로그인 시점부터 **14일 절대 만료**다. Refresh 회전은 절대 만료를 늘리지 않는다.
Refresh는 난수 원문을 쿠키로 보내고 DB에는 SHA-256만 저장한다. 이미 회전한 값을 재사용하면
같은 계열을 폐기한다. 매 요청에서 DB를 읽는 비용과 회전 경합 시 재로그인하는 대가가 있다.

| 함께 검토한 방법 | 이번에 고르지 않은 이유 |
| --- | --- |
| 불투명 서버 세션 하나 | 더 간단하지만, JWT 검증과 Refresh 회전·재사용 탐지를 구현하는 학습 방향을 선택했다 |
| 무상태 JWT만 사용 | 로그아웃 뒤에도 만료 전 토큰이 통하므로 즉시 폐기 기준을 만족하지 못한다 |
| Flask-Login + Flask-Session | 가능한 대안이다. 이번에는 수명·계열 폐기·소유권 경로를 직접 설명하고 검증하는 구현을 선택했다 |
| 외부 인증 서비스 | 선택한 서비스에 따라 저장된 비밀번호 해시를 직접 조회하는 과제 증거가 제한될 수 있다 |
| bcrypt·scrypt·PBKDF2 | 비교 측정 후보로 남겼다. 이번 구현은 메모리 비용과 salt 관리가 명시적인 Argon2id로 통일했다 |

쿠키 운반은 다음과 같다. 실제 브라우저에는 모두 `Secure`를 설정하고 Domain은 지정하지 않는다.

| 쿠키 | HttpOnly | SameSite | Path |
| --- | --- | --- | --- |
| `__Host-pds_access` | 예 | Lax | `/` |
| `__Secure-pds_refresh` | 예 | Strict | `/api/auth` |
| `__Host-pds_csrf` | 아니오 | Lax | `/` |

인증 토큰을 URL이나 localStorage에 넣지 않는다. JavaScript는 CSRF 쿠키만 읽어
`X-CSRF-Token` 헤더에 복사한다. 상태 변경은 JSON·Origin 검사와 CSRF 검사를 거친다.

## ③ 어디를 어떻게 고쳤나

경로는 저장소 루트 기준이다. 해싱과 서명 알고리즘 자체는 구현하지 않았다.

| 흐름 | 요청과 소스 경로 | 결과 |
| --- | --- | --- |
| 가입 | `frontend/src/auth/CredentialsPage.tsx` → `POST /api/auth/signup` → `backend/app/api/auth.py:signup` → `services/accounts.py:parse_credentials, create_account` → `security/passwords.py:hash_password` | 계정 저장 201, 중복 이메일은 DB unique 제약으로 409 |
| 로그인 | 같은 화면 → `POST /api/auth/login` → `api/auth.py:login` → `services/accounts.py:authenticate` → `security/passwords.py:verify_password` → `services/sessions.py:open_session` → `auth/cookies.py:attach_session` | 검증 후 세 쿠키 발급; 없는 이메일·틀린 비밀번호는 같은 401 응답 |
| 로그아웃 | `frontend/src/auth/AccountBar.tsx` → `POST /api/auth/logout` → `api/auth.py:logout` → `auth/guards.py:login_required` → `services/sessions.py:end_session` → `auth/cookies.py:clear_session` | 서버 세션 폐기 후 쿠키 삭제; 기존 값을 재전송해도 401 |
| 자료 조회 | `frontend/src/api/plans.ts` → `GET /api/plans` 또는 `/api/plans/<id>` → `api/plans.py:list_plans, get_plan` → `auth/guards.py:login_required` → `services/ownership.py:plans_for, owned_plan` | 인증된 소유자의 행만 반환; 남의 ID는 404 |

인증 거절은 `backend/app/auth/guards.py`, 소유권 조회·거절은
`backend/app/services/ownership.py`, CSRF 거절은 `backend/app/auth/csrf.py`에서 확인한다.
화면 관문은 `frontend/src/auth/RequireSession.tsx`, 인증 상태는 `SessionProvider.tsx`,
Refresh 직렬화와 재시도는 `frontend/src/api/http.ts`에 있다.

T06 자료 이관은 `backend/scripts/claim_t06_data.py`가 고정 ID 목록으로 수행한다.
`deploy/start.sh`는 계정 추가 revision까지 이동 → claim → 나머지 migration 순서다.
NOT NULL 적용 전에 소유자를 채운다. 삭제 대상이 포함되므로 백업을 먼저 확보해야 한다.
현재 이관 코드는 검증했지만 운영 DB에서 이관을 완료한 증거는 없다.

## ④ 안 열리는 것을 확인한 기록

아래는 `backend/scripts/collect_auth_evidence.py`가 일회용 SQLite에서 실제 요청해 수집한
증거를 요약한 것이다. 각 링크에는 요청 방식·주소·가린 쿠키·응답 본문이 있다.
운영 브라우저의 쿠키 보관과 PostgreSQL 경합 검증은 별도 배포 확인 항목이다.

| 확인 | 성공한 요청 | 거절된 요청 | 전체 기록 |
| --- | --- | --- | --- |
| 가입·로그인 | 새 이메일 `POST /api/auth/signup` 201, 정상 로그인 200 | 중복 가입 409; 틀린 비밀번호·없는 이메일 로그인 모두 같은 401 | [01](T07-EVIDENCE/01-signup-login-logout.md) |
| 로그아웃 뒤 기존 값 재사용 | 기존 쿠키로 `GET /api/auth/me` 200 | 로그아웃 후 보관한 **같은 쿠키 원문을 복원**해 같은 GET → 401 | [03](T07-EVIDENCE/03-logout-replay-blocked.md) |
| 타인 자료 읽기 | A가 자기 계획 GET → 200 | A→B, B→A 계획 GET → 404 | [08](T07-EVIDENCE/08-cross-user-access-blocked.md) |
| 타인 자료 변경 | 각자 계획·할 일 생성 성공, 자기 목록 조회 200 | 양방향 PATCH 계획·DELETE 할 일 → 404. DELETE에도 JSON과 CSRF 헤더 전송 | [08](T07-EVIDENCE/08-cross-user-access-blocked.md) |
| 무인증·목록 격리 | A의 `GET /api/plans` 200, 자기 자료만 반환 | 쿠키 없는 동일 GET → 401; 다른 계정 식별자를 보낸 요청도 소유권을 바꾸지 못함 | [08](T07-EVIDENCE/08-cross-user-access-blocked.md) |

추가 보안 동작은 [Refresh 회전](T07-EVIDENCE/04-refresh-rotation.md),
[재사용 탐지](T07-EVIDENCE/05-refresh-reuse-detected.md), [CSRF](T07-EVIDENCE/06-csrf-blocked.md),
[로그인 제한](T07-EVIDENCE/07-bruteforce-blocked.md), [만료](T07-EVIDENCE/09-session-expiration.md),
[보안 이벤트](T07-EVIDENCE/10-security-events.md)에 성공·거절을 함께 기록했다.
[합계 검산](T07-EVIDENCE/11-totals.md)은 합성 데이터 계산 검사이며 **실제 5일 사용 증거가 아니다**.

## ⑤ AI와 나

AI에게 맡긴 일: 인증 API·화면·마이그레이션·회전 및 폐기·소유권 검사 구현,
자동 검사와 증거 수집, 구현 경로를 설명하는 문서 초안 작성.

내가 직접 판단한 일: **본인 작성 대기.** 기존 인증 방향 결정 문서와 실제 선택을 보고
본인의 이유와 감수한 대가를 작성해야 한다.

AI 제안을 따르지 않은 일: **본인 작성 대기.** 실제 사례와 이유를 적거나, 없었다면
왜 없었는지 적는다. AI가 본인의 판단을 대신 지어내지 않는다.

## ⑥ 아직 못 막은 것

현재 한계와 이유의 전체 목록은 [설계 11절](T07-ARCHITECTURE.md#11-⑥-아직-못-막은-것-c130)을
이 설명서의 일부로 함께 읽는다. 이 목록을 별도로 복제해 서로 다른 상태를 적지 않는다.
예를 들어 비밀번호 재설정과 이메일 소유 확인이 없어 비밀번호를 잊으면 계정을 되찾지
못하고 남의 이메일로 가입할 수 있다. 가입 속도 제한도 없어 대량 계정 생성이 가능하다.
따라서 현재 구현을 일반 사용자 대상 인증 서비스의 완성형으로 보지 않는다.

이번 증거 검토에서도 쿠키 없이 받은 401과 잘못된 형식으로 받은 415가 각각
세션 폐기·소유권 차단 증거처럼 기록돼 있었다. 수집 요청을 고쳐 기존 쿠키 재사용 401과
유효한 JSON 삭제 요청의 404를 다시 확인했다. 거절 코드가 있다는 것만으로 원하는
보안 경로를 검증했다고 판단할 수 없다는 한계도 남긴다.

관찰은 [고정 프로토콜](T07-STUDY-PROTOCOL.md)을 따른다. 배포 다음 날부터 실제 달력 5일,
2일차 기록 뒤·3일차 기록 앞의 규칙 변경, 실제 합계 검산을 마친 뒤 제출한다.
