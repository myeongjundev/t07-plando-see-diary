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
- **백그라운드로 돌린다.** 0.1 코어에서 몇 분 걸리는 작업이 포트를 붙잡고 있으면
  헬스체크가 먼저 죽는다. waitress가 먼저 뜨고, 10초 뒤 작업이 시작된다.
- 결과는 **로그로만** 나온다. Free에는 가져올 디스크가 없고, 엔드포인트를 열면 공개
  주소에 디버그 문이 하나 생긴다. `===== BOOT_TASK ... BEGIN/END =====`로 감싸
  로그 뷰어에서 그 블록만 그대로 들어낼 수 있게 했다.
- 노출되는 값 없음: 벤치마크는 합성 비밀번호(`bench-only-not-a-real-password-1234`,
  스크립트에 그대로 적혀 있다)만 쓰고, 저장된 해시는 **길이와 접두사만** 출력한다.

## 실행

전부 git으로 돈다. 대시보드에서 고칠 것은 없다.

1. `render.yaml`의 `BOOT_TASK`를 `"bench_password_hashing"`으로 바꾼다.

```bash
git commit -am "Measure hashing cost on the deployed instance" && git push
```

2. 배포가 Live가 되면 Render 로그에서 `===== BOOT_TASK bench_password_hashing BEGIN =====`
   부터 `END`까지를 복사해 `docs/T07-EVIDENCE/00-hash-bench-render.md`로 저장한다.
   0.1 코어라 **표가 다 찍히기까지 수 분** 걸린다. 마지막 줄이 나올 때까지 기다린다.

3. `BOOT_TASK`를 `"none"`으로 되돌린다.

```bash
git commit -am "Put the boot task back to none" && git push
```

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
