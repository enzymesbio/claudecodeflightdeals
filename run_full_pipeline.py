"""
Full Pipeline Runner

Runs the complete scan → monitor → verify → drill → generate → archive sequence.
Self-monitoring: after scanning, checks per-city results and auto-retries blocked cities.

Stages:
  1. bug_fare_scanner.py      → scanner_results.json     (round-trip Explore)
  1m. monitor.py              → health check + auto-retry blocked cities
  2. oneway_scanner.py        → oneway_results.json      (one-way Explore)
  3. deep_verify_all.py       → deep_verify_all_results.json (Playwright booking verify)
  4. drill_promising.py       → drill_results.json       (duration/stopover/open-jaw)
  5. generate_verification_page.py → bug_fare_verify.html
  6. archive_run.py           → archive/{slug}/ + index.html

Usage:
    python run_full_pipeline.py           # full run
    python run_full_pipeline.py --from 3  # resume from stage 3
    python run_full_pipeline.py --only 5  # only stage 5 (HTML gen)
    python run_full_pipeline.py --skip-monitor  # skip health check
"""
import sys, os, subprocess, time, argparse, json, threading
from datetime import datetime, timezone, timedelta

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))  # works on both Windows and Railway/Linux
SHANGHAI_TZ = timezone(timedelta(hours=8))
PYTHON      = sys.executable


N_SCAN_WORKERS = 4  # parallel scanner subprocesses


def ts():
    return datetime.now(SHANGHAI_TZ).strftime('%H:%M:%S')


def run_parallel_scanner(timeout=3600):
    """Run bug_fare_scanner.py across N_SCAN_WORKERS parallel subprocesses.
    Cities are split interleaved (e.g. 0,4,8,12 / 1,5,9,13 / ...) for even load.
    Each worker writes to scanner_partial_N.json; results are merged afterwards.
    Returns True if at least one worker succeeded.
    """
    # Get city keys from entities (same source as scanner's ORIGIN_CITIES)
    try:
        sys.path.insert(0, BASE_DIR)
        from entities import ORIGINS
        all_city_keys = [v['city'].lower().replace(' ', '_') for v in ORIGINS.values()]
    except Exception as e:
        print(f"  [parallel scanner] Could not load city list: {e} — falling back to single run")
        return run('bug_fare_scanner.py', 'Stage 1: Round-trip Explore scan (fallback)', timeout)

    # Split interleaved across workers
    groups = [all_city_keys[i::N_SCAN_WORKERS] for i in range(N_SCAN_WORKERS)]
    partial_files = [os.path.join(BASE_DIR, f'scanner_partial_{i}.json') for i in range(N_SCAN_WORKERS)]
    worker_errors = []
    lock = threading.Lock()

    def run_worker(idx, city_keys, out_file):
        cities_arg = ','.join(city_keys)
        cmd = [PYTHON, os.path.join(BASE_DIR, 'bug_fare_scanner.py'),
               '--cities', cities_arg, '--output', out_file]
        print(f"  [worker {idx}] cities: {', '.join(city_keys)}")
        result = subprocess.run(cmd, cwd=BASE_DIR, timeout=timeout)
        if result.returncode != 0:
            with lock:
                worker_errors.append(idx)
            print(f"  [worker {idx}] FAILED (exit {result.returncode})")
        else:
            print(f"  [worker {idx}] done → {os.path.basename(out_file)}")

    print(f"\n[{ts()}] ▶ Stage 1: Parallel scan — {N_SCAN_WORKERS} workers × {len(all_city_keys)//N_SCAN_WORKERS}–{(len(all_city_keys)+N_SCAN_WORKERS-1)//N_SCAN_WORKERS} cities each")
    start = time.time()
    threads = []
    for i, (grp, pf) in enumerate(zip(groups, partial_files)):
        if not grp:
            continue
        t = threading.Thread(target=run_worker, args=(i, grp, pf), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    elapsed = time.time() - start
    print(f"[{ts()}] {'✓' if not worker_errors else '⚠'} Parallel scan done ({elapsed:.0f}s) — {len(worker_errors)} worker(s) failed")

    # Merge partial results into scanner_results.json
    merged = {
        'scan_timestamp': datetime.now(SHANGHAI_TZ).isoformat(),
        'scan_date': 'flexible',
        'cities_scanned': [],
        'cabins_scanned': [1, 2, 3, 4],
        'destinations': [],
        'bug_fares': [],
        'cheap_fares': [],
        'summary': {},
    }
    loaded = 0
    for pf in partial_files:
        if os.path.exists(pf):
            try:
                with open(pf, encoding='utf-8') as f:
                    part = json.load(f)
                merged['cities_scanned'].extend(part.get('cities_scanned', []))
                merged['destinations'].extend(part.get('destinations', []))
                merged['bug_fares'].extend(part.get('bug_fares', []))
                merged['cheap_fares'].extend(part.get('cheap_fares', []))
                loaded += 1
            except Exception as e:
                print(f"  [merge] Could not load {pf}: {e}")

    if loaded == 0:
        print(f"  [merge] No partial results — scan failed entirely")
        return False

    merged['summary'] = {
        'total_destinations': len(merged['destinations']),
        'bug_fares_found': len(merged['bug_fares']),
        'cheap_fares_found': len(merged['cheap_fares']),
        'workers_succeeded': loaded,
        'workers_failed': len(worker_errors),
    }
    out = os.path.join(BASE_DIR, 'scanner_results.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"  [merge] {loaded}/{N_SCAN_WORKERS} workers merged → {len(merged['destinations'])} destinations → {out}")
    return loaded > 0


def run(script, label, timeout=3600, extra_args=None):
    print(f"\n[{ts()}] ▶ Stage: {label}")
    cmd = [PYTHON, os.path.join(BASE_DIR, script)] + (extra_args or [])
    print(f"  Running: {' '.join(cmd)}")
    start = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=False, timeout=timeout)
    elapsed = time.time() - start
    status = 'OK' if result.returncode == 0 else f'FAILED (code {result.returncode})'
    print(f"[{ts()}] {'✓' if result.returncode == 0 else '✗'} {label} — {status} ({elapsed:.0f}s)")
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from', dest='from_stage', type=int, default=1)
    parser.add_argument('--only', dest='only_stage', type=int, default=None)
    parser.add_argument('--skip-monitor', action='store_true',
                        help='Skip health check after scanner')
    args = parser.parse_args()

    stages = [
        (2, 'oneway_scanner.py',             'One-way Explore scan',         3600),
        (3, 'deep_verify_all.py',            'Deep verify bookable fares',   3600),
        (4, 'drill_promising.py',            'Drill duration/stopover',      7200),
        (5, 'generate_verification_page.py', 'Generate HTML',                 120),
        (6, 'archive_run.py',                'Archive + update index',         60),
    ]

    print('=' * 65)
    print(f"  FULL PIPELINE — {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print('=' * 65)

    failed = False

    # Stage 1: parallel scanner
    if not args.only_stage and args.from_stage <= 1:
        ok = run_parallel_scanner(timeout=3600)
        if not ok:
            failed = True
            print(f"  WARNING: Stage 1 (parallel scan) failed, continuing...")
        # Stage 1m: health check + auto-retry
        if not args.skip_monitor:
            print(f"\n[{ts()}] ▶ Stage 1m: Health check + auto-retry")
            monitor_ok = run('monitor.py', 'Stage 1m: Monitor + auto-retry', timeout=1800)
            if not monitor_ok:
                print(f"  ⚠ Monitor flagged issues — proceeding anyway with best available data")
    elif args.only_stage == 1:
        ok = run_parallel_scanner(timeout=3600)
        if not ok:
            failed = True

    for num, script, label, timeout in stages:
        if args.only_stage and num != args.only_stage:
            continue
        if num < args.from_stage:
            print(f"  [skip] Stage {num}: {label}")
            continue
        if failed and num not in (5, 6):
            print(f"  [skip due to failure] Stage {num}: {label}")
            continue

        ok = run(script, f"Stage {num}: {label}", timeout=timeout)
        if not ok:
            failed = True
            print(f"  WARNING: Stage {num} failed, continuing...")

    print(f"\n{'=' * 65}")
    status = 'COMPLETE' if not failed else 'COMPLETED WITH ERRORS'
    print(f"  PIPELINE {status}")
    print(f"  HTML:  {BASE_DIR}/bug_fare_verify.html")
    print(f"  Index: {BASE_DIR}/index.html")
    print(f"{'=' * 65}")


if __name__ == '__main__':
    main()
