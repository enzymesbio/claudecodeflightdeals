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
import sys, os, subprocess, time, argparse
from datetime import datetime, timezone, timedelta

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR    = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))
PYTHON      = sys.executable


def ts():
    return datetime.now(SHANGHAI_TZ).strftime('%H:%M:%S')

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
        (1, 'bug_fare_scanner.py',           'Round-trip Explore scan',      3600),
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

        # After stage 1 (scanner), run health check + auto-retry
        if num == 1 and not args.skip_monitor and not args.only_stage:
            print(f"\n[{ts()}] ▶ Stage 1m: Health check + auto-retry")
            monitor_ok = run('monitor.py', 'Stage 1m: Monitor + auto-retry',
                             timeout=1800)  # up to 30 min for retries
            if not monitor_ok:
                print(f"  ⚠ Monitor flagged issues — proceeding anyway with best available data")

    print(f"\n{'=' * 65}")
    status = 'COMPLETE' if not failed else 'COMPLETED WITH ERRORS'
    print(f"  PIPELINE {status}")
    print(f"  HTML:  {BASE_DIR}/bug_fare_verify.html")
    print(f"  Index: {BASE_DIR}/index.html")
    print(f"{'=' * 65}")


if __name__ == '__main__':
    main()
