"""Time password hashing candidates on this machine against a login-latency budget.

Verification time is the login path and the number that decides the choice; hashing
time only affects signup. Memory costs are declared, not measured: Argon2 and scrypt
allocate inside C and tracemalloc never sees it.

Run this on the deployment target too. A laptop and a Render Free instance (0.1 CPU)
do not produce comparable numbers, and the number that matters is the deployed one.

    python backend/scripts/bench_password_hashing.py --markdown docs/T07-EVIDENCE/00-hash-bench.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError, version

# Synthetic. Never put a real credential here: this file is committed.
BENCH_PASSWORD = 'bench-only-not-a-real-password-1234'


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return 'not installed'


def build_candidates(password: str) -> list[dict]:
    """Each candidate carries its own hash/verify closures and declared memory cost."""
    candidates: list[dict] = []

    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import VerificationError

        # OWASP lists these two as equivalent minimums; argon2-cffi's own defaults are
        # far heavier and are included to show what "just use the defaults" would cost.
        argon2_params = [
            ('OWASP min', dict(time_cost=2, memory_cost=19456, parallelism=1)),
            ('OWASP alt', dict(time_cost=1, memory_cost=47104, parallelism=1)),
            ('argon2-cffi defaults', dict(time_cost=3, memory_cost=65536, parallelism=4)),
        ]
        for label, params in argon2_params:
            hasher = PasswordHasher(hash_len=32, salt_len=16, **params)

            def make(hasher=hasher):
                def do_hash(pw: str) -> str:
                    return hasher.hash(pw)

                def do_verify(stored: str, pw: str) -> bool:
                    try:
                        return hasher.verify(stored, pw)
                    except VerificationError:
                        return False

                return do_hash, do_verify

            do_hash, do_verify = make()
            candidates.append({
                'family': 'argon2id',
                'label': label,
                'params': 'm={memory_cost}KiB t={time_cost} p={parallelism}'.format(**params),
                'memory_kib': params['memory_cost'],
                'library': f"argon2-cffi {package_version('argon2-cffi')}",
                'hash': do_hash,
                'verify': do_verify,
            })
    except ImportError:
        pass

    try:
        import bcrypt

        for rounds in (10, 11, 12, 13):
            def make(rounds=rounds):
                def do_hash(pw: str) -> str:
                    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds)).decode()

                def do_verify(stored: str, pw: str) -> bool:
                    return bcrypt.checkpw(pw.encode(), stored.encode())

                return do_hash, do_verify

            do_hash, do_verify = make()
            candidates.append({
                'family': 'bcrypt',
                'label': f'cost {rounds}',
                'params': f'cost={rounds}',
                'memory_kib': 4,  # bcrypt's working set is fixed and tiny by design.
                'library': f"bcrypt {package_version('bcrypt')}",
                'hash': do_hash,
                'verify': do_verify,
            })
    except ImportError:
        pass

    # Werkzeug ships with Flask, so these two cost no new dependency.
    from werkzeug.security import check_password_hash, generate_password_hash

    werkzeug_methods = [
        ('scrypt', 'Werkzeug default', 'scrypt:32768:8:1', 32768 * 8 * 128 // 1024),
        ('scrypt', 'lighter', 'scrypt:16384:8:1', 16384 * 8 * 128 // 1024),
        ('pbkdf2', 'OWASP 600k', 'pbkdf2:sha256:600000', 0),
        ('pbkdf2', 'Werkzeug default', 'pbkdf2:sha256', 0),
    ]
    for family, label, method, memory_kib in werkzeug_methods:
        def make(method=method):
            def do_hash(pw: str) -> str:
                return generate_password_hash(pw, method=method)

            def do_verify(stored: str, pw: str) -> bool:
                return check_password_hash(stored, pw)

            return do_hash, do_verify

        do_hash, do_verify = make()
        candidates.append({
            'family': family,
            'label': label,
            'params': method,
            'memory_kib': memory_kib,
            'library': f"werkzeug {package_version('werkzeug')}",
            'hash': do_hash,
            'verify': do_verify,
        })

    return candidates


def time_ms(fn, *args) -> tuple[float, object]:
    start = time.perf_counter()
    result = fn(*args)
    return (time.perf_counter() - start) * 1000, result


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank, so the answer is always a value that was actually observed.

    Interpolating between two samples invents a number, and with the handful of
    repeats this affords on a tenth of a core there is not enough data for the
    invented one to be better than the real one next to it.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


PROC_STATUS = '/proc/self/status'


def read_rss_kib(path: str = PROC_STATUS) -> int | None:
    """Resident set size right now, in KiB, or None where it cannot be read.

    /proc is the only source here that reports the memory Argon2 and scrypt
    actually take: they allocate inside C, where tracemalloc never sees it, and
    the declared cost is a parameter rather than a measurement. Linux only,
    which is the platform that matters -- the deployed instance is a container.

    `path` is a parameter so this can be tested off Linux. It is the one piece
    of the benchmark that only ever executes on the deployed instance, where a
    parsing mistake costs another deploy to find.
    """
    try:
        with open(path, encoding='ascii') as handle:
            for line in handle:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


class RssPeak:
    """Sample RSS on a background thread and keep the highest reading.

    ru_maxrss would be cheaper but it is a high-water mark for the whole
    process and never comes back down, so the first heavy candidate would make
    every later one look free. Sampling the current value gives each candidate
    its own peak.

    The sampler holds the GIL only long enough to read one small file, and both
    argon2-cffi and bcrypt release the GIL while hashing, so this costs the
    measurement very little even on a tenth of a core.
    """

    def __init__(self, interval_s: float = 0.02) -> None:
        self.interval_s = interval_s
        self.peak_kib: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        while not self._stop.is_set():
            current = read_rss_kib()
            if current is not None and (self.peak_kib is None or current > self.peak_kib):
                self.peak_kib = current
            self._stop.wait(self.interval_s)

    def __enter__(self) -> RssPeak:
        if read_rss_kib() is None:
            return self  # Nothing to sample on this platform; peak stays None.
        self.peak_kib = read_rss_kib()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def concurrent_verify_ms(candidate: dict, stored: str, password: str, workers: int) -> tuple[float, int | None]:
    """Wall time for `workers` verifications that all start together.

    This is the number a login queue actually feels. Waitress serves with
    threads and both libraries drop the GIL while hashing, so threads here model
    the deployed server rather than approximating it.

    A barrier makes them start together; without it the first worker can finish
    before the last one starts, and the result is a serial run wearing the word
    concurrent.
    """
    barrier = threading.Barrier(workers)

    def one() -> bool:
        barrier.wait(timeout=60)
        return candidate['verify'](stored, password)

    with RssPeak() as rss:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda _: one(), range(workers)))
        elapsed_ms = (time.perf_counter() - start) * 1000
    if not all(results):
        raise SystemExit(f"{candidate['family']} {candidate['label']}: concurrent verify rejected a good password")
    return elapsed_ms, rss.peak_kib


def measure(candidate: dict, password: str, repeats: int, budget_ms: float, workers: list[int]) -> dict:
    hash_times: list[float] = []
    verify_times: list[float] = []
    stored = candidate['hash'](password)  # Warm up: first call may load lazily.
    with RssPeak() as single_rss:
        for _ in range(repeats):
            elapsed, stored = time_ms(candidate['hash'], password)
            hash_times.append(elapsed)
            elapsed, ok = time_ms(candidate['verify'], stored, password)
            verify_times.append(elapsed)
            if not ok:
                raise SystemExit(f"{candidate['family']} {candidate['label']}: verify rejected its own hash")
    # A wrong password must cost about the same, or the timing itself leaks.
    wrong_ms, wrong_ok = time_ms(candidate['verify'], stored, password + 'x')
    if wrong_ok:
        raise SystemExit(f"{candidate['family']} {candidate['label']}: verify accepted a wrong password")
    # Two hashes of one password must differ, or the salt is missing (T07-C104).
    salted = candidate['hash'](password) != candidate['hash'](password)

    # Concurrency only for candidates that fit on their own. A candidate already
    # over budget with one login is not going to be rescued by four, and on a
    # tenth of a core these runs are the expensive part of the benchmark.
    verify_p50 = percentile(verify_times, 0.50)
    concurrency: dict[int, dict] = {}
    if verify_p50 <= budget_ms:
        for count in workers:
            elapsed_ms, peak_kib = concurrent_verify_ms(candidate, stored, password, count)
            concurrency[count] = {'wall_ms': elapsed_ms, 'peak_rss_kib': peak_kib}
    return {
        'family': candidate['family'],
        'label': candidate['label'],
        'params': candidate['params'],
        'memory_kib': candidate['memory_kib'],
        'library': candidate['library'],
        'hash_ms': statistics.median(hash_times),
        'verify_ms': verify_p50,
        'verify_p50_ms': verify_p50,
        # The tail is what a user meets on a bad day, and on a shared tenth of a
        # core the gap between it and the median is the scheduling, not the
        # algorithm. Choosing on the median alone hides that.
        'verify_p95_ms': percentile(verify_times, 0.95),
        'verify_min_ms': min(verify_times),
        'verify_samples': len(verify_times),
        'single_peak_rss_kib': single_rss.peak_kib,
        'concurrency': {str(count): value for count, value in concurrency.items()},
        'wrong_password_ms': wrong_ms,
        'salted': salted,
        'stored_length': len(stored),
        'stored_prefix': stored[:stored.index('$', 1) + 1] if stored.startswith('$') else stored.split('$')[0] + '$',
    }


def cpu_index() -> float:
    """Fixed C-side workload, so numbers from two machines can be put side by side.

    This is an anchor, not a conversion factor: it uses no memory, so it says nothing
    about how a memory-hard candidate will behave on a small instance.
    """
    elapsed, _ = time_ms(hashlib.pbkdf2_hmac, 'sha256', b'anchor', b'anchor', 200_000)
    return elapsed


def bcrypt_truncation() -> str | None:
    """bcrypt ignores everything past 72 bytes. Korean text hits that at 24 characters."""
    try:
        import bcrypt
    except ImportError:
        return None
    base = '가' * 24  # 24 * 3 bytes = 72
    longer = base + '나'
    try:
        stored = bcrypt.hashpw(base.encode(), bcrypt.gensalt(4))
        ignored = bcrypt.checkpw(longer.encode(), stored)
    except ValueError as exc:
        return f'refuses input over 72 bytes ({exc})'
    return 'silently ignores characters past 72 bytes' if ignored else 'does not truncate at 72 bytes'


def kib(value: int | None) -> str:
    """KiB as MiB, or an honest dash where the platform would not say."""
    if value is None:
        return '—'
    return f'{value / 1024:.0f} MiB'


def render(rows: list[dict], meta: dict, budget_ms: float) -> str:
    lines = [
        '# 비밀번호 해싱 비용 측정',
        '',
        f"- 측정 시각: {meta['measured_at']}",
        f"- 기계: {meta['platform']} · CPU {meta['cpu_count']}코어 · Python {meta['python']}",
        f"- CPU 기준점(pbkdf2 200k 반복): **{meta['cpu_index_ms']:.1f} ms** — 다른 기계의 표와 나란히 놓을 때 쓴다",
        f"- 예산: 검증 **{budget_ms:.0f} ms** 안쪽",
        '',
        '검증 시간이 로그인 지연이고, 해시 시간은 가입에만 붙는다. **선언 메모리**는 매개변수이지',
        '측정값이 아니다 — C 안에서 잡히므로 파이썬이 재지 못한다. 그래서 실제로 쓴 양은',
        '`/proc/self/status`의 RSS를 표본으로 떠서 따로 적는다.',
        '',
        '| 방식 | 매개변수 | 선언 메모리 | 해시(ms) | 검증 p50 | 검증 p95 | 예산 | 소금 |',
        '| --- | --- | ---: | ---: | ---: | ---: | --- | --- |',
    ]
    for row in sorted(rows, key=lambda r: r['verify_p50_ms']):
        memory = f"{row['memory_kib'] / 1024:.0f} MiB" if row['memory_kib'] >= 1024 else f"{row['memory_kib']} KiB"
        verdict = '✅ 들어옴' if row['verify_p95_ms'] <= budget_ms else (
            '⚠ p95 초과' if row['verify_p50_ms'] <= budget_ms else '❌ 초과')
        lines.append(
            f"| {row['family']} {row['label']} | `{row['params']}` | {memory} | "
            f"{row['hash_ms']:.0f} | **{row['verify_p50_ms']:.0f}** | {row['verify_p95_ms']:.0f} | {verdict} | "
            f"{'다름' if row['salted'] else '같음 ⚠'} |"
        )
    lines += [
        '',
        f"예산 판정은 **p95** 기준이다. p50만 보면 열에 하나가 예산을 넘는 설정을 골라 놓고",
        f"통과했다고 적게 된다. `⚠ p95 초과`는 중앙값은 들어오지만 꼬리가 {budget_ms:.0f}ms를",
        '넘는다는 뜻이고, 고를 수는 있으나 그렇게 적어야 한다.',
        '',
        '## 동시 로그인과 실제 메모리',
        '',
        '단독 검증이 예산에 든 후보만 잰다. 혼자서 넘긴 것이 넷이 붙는다고 나아지지 않고,',
        '0.1 코어에서 이 측정이 벤치마크에서 가장 비싼 부분이다.',
        '',
        '`동시 N`은 **N건이 동시에 시작해 마지막 하나가 끝날 때까지의 벽시계 시간**이다.',
        'waitress가 스레드로 서빙하고 argon2·bcrypt 모두 해싱 중 GIL을 놓으므로, 스레드로',
        '재는 것이 배포 형태와 같다.',
        '',
    ]
    concurrency_keys = sorted({int(k) for row in rows for k in row['concurrency']})
    if concurrency_keys:
        header = ' | '.join(f'동시 {n} 벽시계 | 동시 {n} peak RSS' for n in concurrency_keys)
        divider = ' | '.join('---: | ---:' for _ in concurrency_keys)
        lines += [
            f"| 방식 | 단독 peak RSS | {header} |",
            f"| --- | ---: | {divider} |",
        ]
        for row in sorted(rows, key=lambda r: r['verify_p50_ms']):
            if not row['concurrency']:
                continue
            cells = []
            for n in concurrency_keys:
                entry = row['concurrency'].get(str(n))
                if entry is None:
                    cells += ['—', '—']
                    continue
                cells.append(f"{entry['wall_ms']:.0f} ms")
                cells.append(kib(entry['peak_rss_kib']))
            lines.append(
                f"| {row['family']} {row['label']} | {kib(row['single_peak_rss_kib'])} | " + ' | '.join(cells) + ' |'
            )
        lines += [
            '',
            f"인스턴스는 **512 MiB**다. peak RSS는 파이썬·Flask·이 스크립트가 이미 쓰고 있는 양을",
            '포함한 프로세스 전체 값이므로, 여기서 512에 가까워지는 후보는 실제 앱에서는 더',
            '가깝다. **500ms는 목표이지, OOM을 무시하고 가장 큰 `m`을 고르라는 규칙이 아니다.**',
        ]
    else:
        lines.append('_예산에 든 후보가 없어 동시성은 재지 않았다._')
    lines += [
        '',
        '## 곁들여 확인한 것',
        '',
        '- 같은 비밀번호를 두 번 해싱한 값이 서로 다른지(T07-C104): 위 표의 「소금」 칸',
        '- 틀린 비밀번호 검증도 같은 비용이 드는지: ' + ', '.join(
            f"{row['family']} {row['label']} {row['wrong_password_ms']:.0f}ms" for row in rows[:3]
        ),
    ]
    if meta.get('bcrypt_truncation'):
        lines.append(f"- bcrypt 길이 제한: {meta['bcrypt_truncation']}")
    lines += [
        '',
        '저장된 해시 값은 이 표에 넣지 않는다. 형식만 적는다: ' + ', '.join(
            sorted({f"`{row['stored_prefix']}…` ({row['stored_length']}자)" for row in rows})
        ),
        '',
    ]
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--budget-ms', type=float, default=500.0, help='login latency budget for verification')
    parser.add_argument('--only', help='substring filter on the family name, e.g. argon2')
    parser.add_argument('--concurrency', default='2,4',
                        help='comma-separated simultaneous-login counts to time, or "" to skip')
    parser.add_argument('--memory-limit-mib', type=float, default=512.0,
                        help='instance memory, for flagging candidates that crowd it')
    parser.add_argument('--markdown', help='write the table to this path')
    parser.add_argument('--json', dest='json_path', help='write raw measurements to this path')
    args = parser.parse_args()

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    candidates = build_candidates(BENCH_PASSWORD)
    if args.only:
        candidates = [c for c in candidates if args.only in c['family']]
    if not candidates:
        raise SystemExit('No candidates available. Install argon2-cffi and bcrypt.')

    workers = [int(n) for n in args.concurrency.split(',') if n.strip()]

    anchor = cpu_index()
    rows = []
    for candidate in candidates:
        # One line per candidate as it finishes. On a tenth of a core the whole
        # run takes minutes, and this is read from a log tail: silence for ten
        # minutes is indistinguishable from a hang.
        print(f"measuring {candidate['family']} {candidate['label']} ...", flush=True)
        rows.append(measure(candidate, BENCH_PASSWORD, args.repeats, args.budget_ms, workers))
    meta = {
        'measured_at': time.strftime('%Y-%m-%d %H:%M:%S %z'),
        'platform': platform.platform(),
        'cpu_count': os.cpu_count(),
        'python': platform.python_version(),
        'cpu_index_ms': anchor,
        'budget_ms': args.budget_ms,
        'repeats': args.repeats,
        'concurrency': workers,
        'memory_limit_mib': args.memory_limit_mib,
        'rss_available': read_rss_kib() is not None,
        'bcrypt_truncation': bcrypt_truncation(),
    }

    table = render(rows, meta, args.budget_ms)
    print(table)

    if args.markdown:
        path = args.markdown
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(table)
        print(f'wrote {path}')
    if args.json_path:
        os.makedirs(os.path.dirname(args.json_path) or '.', exist_ok=True)
        with open(args.json_path, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump({'meta': meta, 'rows': rows}, handle, ensure_ascii=False, indent=2)
        print(f'wrote {args.json_path}')

    # The tail decides, not the median: a setting whose p95 is over budget is
    # over budget for one login in twenty.
    within = [row for row in rows if row['verify_p95_ms'] <= args.budget_ms]
    if not within:
        print(f'\nNothing fits the {args.budget_ms:.0f} ms budget at p95 on this machine.')
        return

    limit_kib = args.memory_limit_mib * 1024
    def crowds_memory(row: dict) -> bool:
        peaks = [c['peak_rss_kib'] for c in row['concurrency'].values() if c['peak_rss_kib']]
        # Two thirds of the instance for hashing alone leaves too little for the
        # app that has to answer the request afterwards.
        return any(peak > limit_kib * 0.66 for peak in peaks)

    roomy = [row for row in within if not crowds_memory(row)]
    best = max(roomy or within, key=lambda r: r['verify_p95_ms'])
    print(f"\nSlowest candidate still inside the budget at p95: {best['family']} {best['label']} "
          f"({best['params']}) at {best['verify_p95_ms']:.0f} ms p95, "
          f"{best['verify_p50_ms']:.0f} ms p50.")
    for row in within:
        if crowds_memory(row):
            print(f"  memory warning: {row['family']} {row['label']} peaks above two thirds of "
                  f"{args.memory_limit_mib:.0f} MiB under concurrency; not recommended here.")
    if not meta['rss_available']:
        print('  RSS was not readable on this platform, so no memory claim is being made.'
              '\n  The number that decides this has to come from the deployed instance.')
    print('That is a latency ranking only. Cost per guess is what an attacker pays, and a'
          '\nmemory-hard candidate buys more of it per millisecond than bcrypt or pbkdf2.')
    print('Re-run this on the deployed instance before deciding.')


if __name__ == '__main__':
    main()
