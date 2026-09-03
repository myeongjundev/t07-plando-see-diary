# 배포 인스턴스에서 해싱 비용을 재는 절차

작성 2026-09-03 · 관련 `docs/T07-AUTH-OPTIONS.md` 6절 · `deploy/start.sh`

## 왜 절차가 따로 필요한가 — Render Free에는 셸이 없다

계획은 "Render Shell에서 벤치마크를 돌린다"였다. **그 문은 닫혀 있다.**

Render 문서가 명시한다: 대시보드 Shell과 SSH는 **유료 웹 서비스·프라이빗 서비스·백그라운드
워커**에만 열린다. Free 웹 서비스는 둘 다 `❌`다. 같은 이유로 Free에서는

- 일회성 잡(one-off job) — 문서가 Free 미지원으로 명시
- 크론 잡 — Free 인스턴스 자체가 없는 서비스 종류

도 쓸 수 없다. 즉 **그 인스턴스에서 실행되는 코드는 웹 서비스 프로세스 하나뿐이다.**

출처: <https://render.com/docs/ssh> · <https://render.com/docs/free>

### 노트북에서 재는 것으로 대신할 수 없는 이유

`0.1 CPU`를 흉내 내는 것(cgroup 쿼터, `docker run --cpus=0.1`)은 **쿼터만 같고 코어가
다르다.** 이 노트북 코어 한 개의 1/10과 Render가 떼어 주는 vCPU의 1/10은 다른 속도다.
후보들이 500ms 예산 앞에서 갈리는 지점이 바로 그 차이 안에 있으므로, 흉내로는 결정의
근거가 못 된다. 재려면 그 기계에서 재야 한다.

## 대안 — 부팅에 얹어 보낸다 (`BOOT_TASK`)

인스턴스에서 도는 것이 웹 서비스뿐이라면, 일회성 명령은 **그 부팅에 얹어야** 한다.
`deploy/start.sh`에 `BOOT_TASK` 분기를 두었다.

- 이름은 **고정 목록**과 대조한다 (`bench_password_hashing` · `claim_t06_data` · `none`).
  환경변수는 원격 입력이 아니지만, 받은 문자열을 그대로 실행하는 셸은 만든 이유보다
  오래 남는다. 이것은 지울 물건이다.
- **벤치마크는 백그라운드로 돌린다.** 0.1 코어에서 몇 분 걸리는 작업이 포트를 붙잡고 있으면
  헬스체크가 먼저 죽는다. waitress가 먼저 뜨고, 10초 뒤 작업이 시작된다.
- 결과는 **로그로만** 나온다. Free에는 가져올 디스크가 없고, 엔드포인트를 열면 공개
  주소에 디버그 문이 하나 생긴다. `===== BOOT_TASK ... BEGIN/END =====`로 감싸
  로그 뷰어에서 그 블록만 그대로 들어낼 수 있게 했다.
- 노출되는 값 없음: 벤치마크는 합성 비밀번호(`bench-only-not-a-real-password-1234`,
  스크립트에 그대로 적혀 있다)만 쓰고, 저장된 해시는 **길이와 접두사만** 출력한다.

## 먼저 — 이 저장소를 보는 서비스가 아직 없다

`t07-plando-see-diary`는 2026-09-03에 새로 만든 저장소다. 라이브인
`t06-plando-see-diary.onrender.com`은 **T06 저장소**를 보고 있으므로, 여기에 푸시해도
아무 배포도 일어나지 않는다.

그리고 그 서비스를 T07로 돌리는 것은 **T06 제출 전까지 막혀 있다**(설계 0절). 돌리는
순간 T06 결과물 URL이 로그인 화면이 되기 때문이다.

### 그래서 벤치마크만 먼저 빼내는 길

측정 하나 때문에 T06 제출을 기다릴 이유는 없다. **버리는 서비스를 하나 세운다.**

1. Render에서 **새 Free 웹 서비스**를 만들고 저장소를 `t07-plando-see-diary`로,
   이름은 `t07-bench` 같은 임시 이름으로 둔다. 이름이 다르므로 **t06 주소는 손대지
   않는다.**
2. `DATABASE_URL`에 **T06 Neon 주소를 그대로** 넣는다. 아직 T07 마이그레이션이 없으므로
   부팅의 `flask db upgrade`는 아무것도 바꾸지 않는다 — 그게 없으면 `REQUIRE_POSTGRES=1`
   에서 컨테이너가 죽어 벤치마크까지 가지도 못한다.
3. 로그에서 표를 받는다(아래 「실행」 2번).
4. **서비스를 지운다.** 측정이 끝나면 남을 이유가 없다.

이 서비스는 공개 주소를 하나 갖지만, T07 코드는 아직 인증이 없는 T06 화면 그대로이고
합성 자료만 들어 있다. 그래도 오래 두지 않는다.

## 실행

서비스가 생긴 뒤로는 전부 git으로 돈다. 대시보드에서 고칠 것은 `DATABASE_URL`뿐이다.

1. `render.yaml`의 `BOOT_TASK`를 `"bench_password_hashing"`으로 바꾼다.
   (2026-09-03 현재 **이미 켜져 있다.** 서비스만 만들면 첫 배포에서 바로 돈다.)

```bash
git commit -am "Measure hashing cost on the deployed instance" && git push
```

2. 배포가 Live가 되면 Render 로그에서 `===== BOOT_TASK bench_password_hashing BEGIN =====`
   부터 `END`까지를 복사해 `docs/T07-EVIDENCE/00-hash-bench-render.md`로 저장한다.
   0.1 코어라 **표가 다 찍히기까지 십수 분** 걸릴 수 있다. 마지막 줄이 나올 때까지 기다린다.
   후보마다 `measuring <이름> ...` 한 줄이 먼저 나오므로, 멈춘 것과 도는 것을 구별할 수 있다.

   표는 세 가지를 준다(설계 1절이 요구한 것):
   - **검증 p50 / p95** — 예산 판정은 **p95**로 한다. p50만 보면 열에 하나가 예산을 넘는
     설정을 골라 놓고 통과했다고 적게 된다
   - **동시 2건·4건 벽시계** — N건이 같이 시작해 마지막이 끝날 때까지. waitress가 스레드로
     서빙하고 두 라이브러리 다 해싱 중 GIL을 놓으므로 스레드 측정이 배포 형태와 같다
   - **peak RSS** — `/proc/self/status`를 표본으로 뜬 실제 사용량. 선언 메모리는 매개변수일
     뿐이고, 512MiB 인스턴스에서 넷이 붙었을 때 터지는지는 이 숫자만 답한다

   단독 검증이 예산에 든 후보만 동시성을 잰다. 혼자 넘긴 것이 넷이 붙어 나아지지 않고,
   0.1 코어에서 이 부분이 제일 비싸다.

3. `BOOT_TASK`를 `"none"`으로 되돌린다.

```bash
git commit -am "Put the boot task back to none" && git push
```

`BOOT_TASK`를 끄지 않은 채로 두면, 나중에 T06 서비스를 T07로 돌렸을 때 **본 배포에서도
벤치마크가 돈다.** 3번은 잊으면 안 되는 단계다.

## 되돌리기

알고리즘이 정해지면 이 장치는 통째로 없앤다. 남겨 두면 쓸 이유가 없는데 남아 있는
실행 경로가 된다.

- `deploy/start.sh` — `case "${BOOT_TASK...}"` 블록 삭제
- `render.yaml` — `BOOT_TASK` · `BOOT_TASK_ARGS` 두 항목 삭제
- `backend/pyproject.toml` — `[project.optional-dependencies] bench` 삭제,
  이긴 후보를 `dependencies`로 올린다
- `Dockerfile` — `".[bench]"`를 `.`으로 되돌린다. `COPY backend/scripts`는
  `claim_t06_data.py`를 같은 방식으로 태워 보내야 하므로 **그때까지는 남긴다**

## 딸려 나온 것 — 자료 이관도 같은 문제다

설계 2절의 T06 자료 이관(`backend/scripts/claim_t06_data.py`, C100)도 배포 인스턴스의
데이터베이스를 상대로 한 번 돌려야 한다. **셸이 없다는 제약은 거기에도 똑같이 걸린다.**
그래서 `BOOT_TASK`의 고정 목록에 그 이름을 미리 넣어 두었다. 비밀번호는 `BOOT_TASK_ARGS`가
아니라 **별도 환경변수(`sync: false`)로 받는다** — `render.yaml`은 커밋되는 파일이고,
인자로 넘기면 로그의 명령줄에도 남는다.

이쪽은 **본 서비스에서** 돌린다. 버리는 벤치마크 서비스에서 돌리면 안 된다 — T06 자료를
상대로 계정을 만드는 일이라, 한 번만, 옳은 곳에서 일어나야 한다.

### 먼저 준비할 것 — 고정 ID 목록

스크립트는 **주인 없는 계획을 하나도 빠짐없이 두 목록 중 하나에** 넣으라고 요구한다.
어느 쪽에도 없는 계획이 있으면 **아무것도 바꾸지 않고 그 ID를 찍으며 멈춘다.** 제목으로
고르지 않는 이유는 설계 2절에 있다 — 부분 문자열은 진짜 자료에도 걸릴 수 있다.

그러니 Neon 콘솔에서 한 번 읽어야 한다:

```sql
SELECT id, title, start_date FROM plans WHERE user_id IS NULL ORDER BY created_at;
```

보고 나서 `CLAIM_PLAN_IDS`(내 것으로 가져올 것)와 `CLAIM_EXCLUDE_PLAN_IDS`(버릴 것)에
쉼표로 넣는다. **제외 목록은 삭제된다.** 되돌릴 수 없으니 두 번 읽는다.

`--apply` 없이 돌리면 **아무것도 바꾸지 않고 무엇을 할지만 보고한다.** 먼저 그렇게
한 번 돌려 건수를 확인하는 것을 권한다.

### claim과 NOT NULL은 같은 배포에 넣지 않는다

현재 `deploy/start.sh`는 BOOT_TASK를 모두 백그라운드로 보내지만, 실제 이관 구현에서는
벤치마크만 그 경로에 남기고 `claim_t06_data`는 `flask db upgrade` 뒤·웹 프로세스 앞에서
**동기 실행**하도록 분리한다. 순서는 `flask db upgrade` → claim → 웹 프로세스다. 따라서
nullable 추가, claim, NOT NULL 변경을 한 commit에 넣으면 NOT NULL 마이그레이션이 claim보다
먼저 실행되어 기존 행에서 실패한다. 본 서비스 전환은 다음 두 배포로 고정한다.

1. 첫 배포에는 `plans.user_id` nullable 추가와 claim 스크립트만 넣는다. BOOT_TASK를
   `claim_t06_data`로 두고, 비밀번호는 별도 `sync: false` 환경변수에서 읽는다.
2. 로그에서 고정 ID별 claim 결과와 `SELECT count(*) FROM plans WHERE user_id IS NULL = 0`을
   확인한다. 스크립트 전체는 한 트랜잭션이며 다시 실행해도 행을 중복 생성하지 않는다.
3. 두 번째 배포에서 BOOT_TASK를 `none`으로 되돌리고 **별도 마이그레이션**으로 NOT NULL을
   건다. 이 배포가 끝나기 전에는 claim 완료라고 기록하지 않는다.

제외할 합성 자료는 제목이나 본문 비교로 고르지 않는다. 미리 검토한 plan/task의 고정 ID
목록만 사용한다. 로그에는 사용자 문장이나 비밀번호를 출력하지 않고 ID별 건수와 NULL 건수만
남긴다.
