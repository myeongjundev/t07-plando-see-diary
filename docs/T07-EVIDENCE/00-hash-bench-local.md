# 비밀번호 해싱 비용 측정

- 측정 시각: 2026-09-03 17:22:02 +0900
- 기계: Windows-11-10.0.26100-SP0 · CPU 16코어 · Python 3.14.7
- CPU 기준점(pbkdf2 200k 반복): **77.3 ms** — 다른 기계의 표와 나란히 놓을 때 쓴다
- 예산: 검증 **500 ms** 안쪽

검증 시간이 로그인 지연이고, 해시 시간은 가입에만 붙는다. 메모리는 선언값이다 —
C 안에서 잡히므로 파이썬이 재지 못한다.

| 방식 | 매개변수 | 선언 메모리 | 해시(ms) | 검증(ms) | 예산 | 소금 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| argon2id OWASP min | `m=19456KiB t=2 p=1` | 19 MiB | 27 | **26** | ✅ 들어옴 | 다름 |
| argon2id OWASP alt | `m=47104KiB t=1 p=1` | 46 MiB | 38 | **38** | ✅ 들어옴 | 다름 |
| bcrypt cost 10 | `cost=10` | 4 KiB | 48 | **48** | ✅ 들어옴 | 다름 |
| scrypt lighter | `scrypt:16384:8:1` | 16 MiB | 50 | **50** | ✅ 들어옴 | 다름 |
| argon2id argon2-cffi defaults | `m=65536KiB t=3 p=4` | 64 MiB | 65 | **65** | ✅ 들어옴 | 다름 |
| bcrypt cost 11 | `cost=11` | 4 KiB | 97 | **97** | ✅ 들어옴 | 다름 |
| scrypt Werkzeug default | `scrypt:32768:8:1` | 32 MiB | 102 | **102** | ✅ 들어옴 | 다름 |
| bcrypt cost 12 | `cost=12` | 4 KiB | 194 | **194** | ✅ 들어옴 | 다름 |
| pbkdf2 OWASP 600k | `pbkdf2:sha256:600000` | 0 KiB | 232 | **231** | ✅ 들어옴 | 다름 |
| pbkdf2 Werkzeug default | `pbkdf2:sha256` | 0 KiB | 387 | **387** | ✅ 들어옴 | 다름 |
| bcrypt cost 13 | `cost=13` | 4 KiB | 388 | **388** | ✅ 들어옴 | 다름 |

## 곁들여 확인한 것

- 같은 비밀번호를 두 번 해싱한 값이 서로 다른지(T07-C104): 위 표의 「소금」 칸
- 틀린 비밀번호 검증도 같은 비용이 드는지: argon2id OWASP min 25ms, argon2id OWASP alt 41ms, argon2id argon2-cffi defaults 65ms
- bcrypt 길이 제한: refuses input over 72 bytes (password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72]))

저장된 해시 값은 이 표에 넣지 않는다. 형식만 적는다: `$2b$…` (60자), `$argon2id$…` (97자), `pbkdf2:sha256:1000000$…` (103자), `pbkdf2:sha256:600000$…` (102자), `scrypt:16384:8:1$…` (162자), `scrypt:32768:8:1$…` (162자)
