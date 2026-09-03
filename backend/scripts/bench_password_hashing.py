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
import os
import platform
import statistics
import sys
import time
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


def measure(candidate: dict, password: str, repeats: int) -> dict:
    hash_times: list[float] = []
    verify_times: list[float] = []
    stored = candidate['hash'](password)  # Warm up: first call may load lazily.
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
    return {
        'family': candidate['family'],
        'label': candidate['label'],
        'params': candidate['params'],
        'memory_kib': candidate['memory_kib'],
        'library': candidate['library'],
        'hash_ms': statistics.median(hash_times),
        'verify_ms': statistics.median(verify_times),
        'verify_min_ms': min(verify_times),
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


def render(rows: list[dict], meta: dict, budget_ms: float) -> str:
    lines = [
        '# 비밀번호 해싱 비용 측정',
        '',
        f"- 측정 시각: {meta['measured_at']}",
        f"- 기계: {meta['platform']} · CPU {meta['cpu_count']}코어 · Python {meta['python']}",
        f"- CPU 기준점(pbkdf2 200k 반복): **{meta['cpu_index_ms']:.1f} ms** — 다른 기계의 표와 나란히 놓을 때 쓴다",
        f"- 예산: 검증 **{budget_ms:.0f} ms** 안쪽",
        '',
        '검증 시간이 로그인 지연이고, 해시 시간은 가입에만 붙는다. 메모리는 선언값이다 —',
        'C 안에서 잡히므로 파이썬이 재지 못한다.',
        '',
        '| 방식 | 매개변수 | 선언 메모리 | 해시(ms) | 검증(ms) | 예산 | 소금 |',
        '| --- | --- | ---: | ---: | ---: | --- | --- |',
    ]
    for row in sorted(rows, key=lambda r: r['verify_ms']):
        memory = f"{row['memory_kib'] / 1024:.0f} MiB" if row['memory_kib'] >= 1024 else f"{row['memory_kib']} KiB"
        verdict = '✅ 들어옴' if row['verify_ms'] <= budget_ms else '❌ 초과'
        lines.append(
            f"| {row['family']} {row['label']} | `{row['params']}` | {memory} | "
            f"{row['hash_ms']:.0f} | **{row['verify_ms']:.0f}** | {verdict} | "
            f"{'다름' if row['salted'] else '같음 ⚠'} |"
        )
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

    anchor = cpu_index()
    rows = [measure(candidate, BENCH_PASSWORD, args.repeats) for candidate in candidates]
    meta = {
        'measured_at': time.strftime('%Y-%m-%d %H:%M:%S %z'),
        'platform': platform.platform(),
        'cpu_count': os.cpu_count(),
        'python': platform.python_version(),
        'cpu_index_ms': anchor,
        'budget_ms': args.budget_ms,
        'repeats': args.repeats,
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

    within = [row for row in rows if row['verify_ms'] <= args.budget_ms]
    if not within:
        print(f'\nNothing fits the {args.budget_ms:.0f} ms budget on this machine.')
        return
    best = max(within, key=lambda r: r['verify_ms'])
    print(f"\nSlowest candidate still inside the budget here: {best['family']} {best['label']} "
          f"({best['params']}) at {best['verify_ms']:.0f} ms.")
    print('That is a latency ranking only. Cost per guess is what an attacker pays, and a'
          '\nmemory-hard candidate buys more of it per millisecond than bcrypt or pbkdf2.')
    print('Re-run this on the deployed instance before deciding.')


if __name__ == '__main__':
    main()
