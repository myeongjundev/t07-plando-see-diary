# Render 배포 인스턴스 비밀번호 해싱 비용 측정

- 측정 시각: 2026-09-06 00:47:48 +0000 (09:47:48 KST)
- Render 서비스: `srv-dabe1mu7bikc73bv2lmg` (Free, 512MiB, 0.1 CPU)
- 배포: `dep-daebf2ht0dsc739ies40`
- 소스: `2723b63c0b93e8dad54f03c3262f08fadeb36922`
- 기계: Linux 6.8.0-1052-aws x86_64, glibc 2.41, 보이는 CPU 8코어, Python 3.12.14
- 인수: `--repeats 3`, 동시성 2·4, 예산 500ms
- CPU 기준점(pbkdf2 200k 반복): 204.3ms

배포 로그의 `===== BOOT_TASK bench_password_hashing BEGIN =====`에서
`END`까지를 전사했다. 측정에는 스크립트의 합성 비밀번호만 쓰였고,
운영 DB를 읽거나 변경하지 않았다. 해시 원문은 남기지 않았다.

| 방식 | 매개변수 | 선언 메모리 | 해시(ms) | 검증 p50 | 검증 p95 | 예산 | salt |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| argon2id OWASP min | `m=19456KiB t=2 p=1` | 19 MiB | 195 | **108** | 197 | ✅ 들어옴 | 다름 |
| scrypt lighter | `scrypt:16384:8:1` | 16 MiB | 299 | **299** | 388 | ✅ 들어옴 | 다름 |
| bcrypt cost 10 | `cost=10` | 4 KiB | 404 | **407** | 492 | ✅ 들어옴 | 다름 |
| argon2id OWASP alt | `m=47104KiB t=1 p=1` | 46 MiB | 495 | **413** | 501 | ⚠ p95 초과 | 다름 |
| scrypt Werkzeug default | `scrypt:32768:8:1` | 32 MiB | 803 | **795** | 795 | ❌ 초과 | 다름 |
| pbkdf2 OWASP 600k | `pbkdf2:sha256:600000` | 0 KiB | 795 | **893** | 898 | ❌ 초과 | 다름 |
| bcrypt cost 11 | `cost=11` | 4 KiB | 895 | **897** | 899 | ❌ 초과 | 다름 |
| pbkdf2 Werkzeug default | `pbkdf2:sha256` | 0 KiB | 1299 | **1493** | 1504 | ❌ 초과 | 다름 |
| argon2id argon2-cffi defaults | `m=65536KiB t=3 p=4` | 64 MiB | 1409 | **1593** | 1593 | ❌ 초과 | 다름 |
| bcrypt cost 12 | `cost=12` | 4 KiB | 1794 | **1800** | 1800 | ❌ 초과 | 다름 |
| bcrypt cost 13 | `cost=13` | 4 KiB | 3592 | **3506** | 3602 | ❌ 초과 | 다름 |

예산 판정은 p95 기준이다. p50만 들어오는 Argon2id OWASP alt는 p95가
501ms여서 경계 초과로 남겼다.

## 동시 로그인과 RSS

| 방식 | 단독 peak RSS | 동시 2 벽시계 | 동시 2 peak RSS | 동시 4 벽시계 | 동시 4 peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| argon2id OWASP min | 51 MiB | 600 ms | 89 MiB | 1009 ms | 146 MiB |
| scrypt lighter | 147 MiB | 689 ms | 147 MiB | 1307 ms | 147 MiB |
| bcrypt cost 10 | 147 MiB | 897 ms | 147 MiB | 1799 ms | 147 MiB |
| argon2id OWASP alt | 192 MiB | 896 ms | 226 MiB | 1906 ms | 303 MiB |

현재 앱 설정인 Argon2id OWASP min은 단독 p95 197ms로 예산을 만족하고,
동시 4건 peak RSS 146MiB로 512MiB 인스턴스에서 충분한 여유를 남겼다.
bcrypt cost 10이 p95 예산 내 가장 느린 후보였지만, 이는 지연 순위일 뿐이다.
구현은 추측당 메모리 비용을 부과하는 Argon2id를 유지한다.

추가 확인:

- 모든 후보에서 같은 비밀번호의 두 해시가 달랐다(T07-C104).
- 틀린 비밀번호 검증: Argon2id min 194ms, alt 403ms, cffi defaults 1407ms.
- 완료 후 Render 환경을 `BOOT_TASK=none`, 빈 `BOOT_TASK_ARGS`로 복구했고
  `dep-daebk4ht0dsc739j04kg`가 Live가 됨을 확인했다.
