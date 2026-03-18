"""
Pipeline Monitor — validates scan results and auto-retries blocked cities.

Checks:
  1. Per-city fare counts vs historical baseline (detects blocks)
  2. Total fare count sanity (detects full scrape failure)
  3. Deep verify booking rate (detects verification failures)
  4. Auto-retries blocked/empty cities with delays

Usage:
    python monitor.py                  # check + auto-retry if needed
    python monitor.py --check-only     # report without retrying
    python monitor.py --force-retry    # retry all cities regardless
"""
import sys, os, json, time, subprocess, argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR    = 'D:/claude/flights'
PYTHON      = sys.executable
SHANGHAI_TZ = timezone(timedelta(hours=8))

SCANNER_FILE = os.path.join(BASE_DIR, 'scanner_results.json')
VERIFY_FILE  = os.path.join(BASE_DIR, 'deep_verify_all_results.json')
ARCHIVE_DIR  = os.path.join(BASE_DIR, 'archive')

# A city returning fewer than this many fares is suspicious
MIN_FARES_PER_CITY = 5

# Cities that historically return very few US destinations (small airports)
LOW_VOLUME_CITIES = {'Fuzhou', 'Xiamen', 'Tianjin', 'Ningbo', 'Qingdao',
                     'Dalian', 'Nanjing', 'Wuhan', 'Savannah'}

# If booking rate drops below this, deep verify may be blocked
MIN_BOOKING_RATE = 0.20  # at least 20% of verified fares should be bookable

# Retry config
MAX_RETRIES     = 3
RETRY_DELAY_SEC = 90   # wait before retrying a blocked city

def ts():
    return datetime.now(SHANGHAI_TZ).strftime('%H:%M:%S')

def load_scanner():
    if not os.path.exists(SCANNER_FILE):
        return None
    with open(SCANNER_FILE, encoding='utf-8') as f:
        return json.load(f)

def load_verify():
    if not os.path.exists(VERIFY_FILE):
        return None
    with open(VERIFY_FILE, encoding='utf-8') as f:
        return json.load(f)

def load_baseline():
    """Load per-city fare counts from the most recent archived run."""
    if not os.path.exists(ARCHIVE_DIR):
        return {}
    runs = sorted(
        [e for e in os.scandir(ARCHIVE_DIR) if e.is_dir()],
        key=lambda e: e.name, reverse=True
    )
    for run in runs:
        path = os.path.join(run.path, 'scanner_results.json')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            counts = defaultdict(int)
            for d in data.get('destinations', []):
                counts[d['origin_city']] += 1
            return dict(counts)
    return {}

def check_scanner(data, baseline):
    """Returns list of problem cities."""
    problems = []
    counts = defaultdict(int)
    for d in data.get('destinations', []):
        counts[d['origin_city']] += 1

    for city, count in sorted(counts.items()):
        threshold = MIN_FARES_PER_CITY if city in LOW_VOLUME_CITIES else MIN_FARES_PER_CITY * 3
        base = baseline.get(city, 0)

        if count == 0:
            problems.append({
                'city': city, 'count': count, 'baseline': base,
                'reason': 'ZERO_RESULTS — likely blocked or failed',
                'severity': 'CRITICAL',
            })
        elif count < threshold:
            if base > 0 and count < base * 0.4:
                problems.append({
                    'city': city, 'count': count, 'baseline': base,
                    'reason': f'LOW_RESULTS ({count} vs baseline {base}) — partial load or soft block',
                    'severity': 'WARNING',
                })

    # Check for cities in baseline that are completely missing from current scan
    scanned = set(counts.keys())
    for city, base_count in baseline.items():
        if city not in scanned and base_count > 0:
            problems.append({
                'city': city, 'count': 0, 'baseline': base_count,
                'reason': 'MISSING — city not in current results at all',
                'severity': 'CRITICAL',
            })

    return problems, dict(counts)

def check_verify(data):
    """Check deep verify results for quality issues."""
    results = data.get('results', [])
    if not results:
        return [{'reason': 'NO_VERIFY_RESULTS', 'severity': 'CRITICAL'}]

    bookable = [r for r in results if r.get('has_booking_page')]
    errors   = [r for r in results if r.get('status') in ('ERROR', 'NO_FLIGHTS')]
    rate     = len(bookable) / len(results) if results else 0

    issues = []
    if rate < MIN_BOOKING_RATE:
        issues.append({
            'reason': f'LOW_BOOKING_RATE ({rate:.0%}, {len(bookable)}/{len(results)}) — Google may be blocking verification',
            'severity': 'WARNING',
        })
    if len(errors) > len(results) * 0.3:
        issues.append({
            'reason': f'HIGH_ERROR_RATE ({len(errors)}/{len(results)} errors)',
            'severity': 'WARNING',
        })
    return issues

def retry_city(city_name, attempt=1):
    """Retry scanning a single city, saving to a temp file."""
    city_key = city_name.lower().replace(' ', '_')
    out_file = os.path.join(BASE_DIR, f'scanner_partial_{city_key}_retry.json')
    print(f"  [{ts()}] Retry {attempt}/{MAX_RETRIES}: {city_name} "
          f"(waiting {RETRY_DELAY_SEC}s first...)")
    time.sleep(RETRY_DELAY_SEC)
    result = subprocess.run(
        [PYTHON, os.path.join(BASE_DIR, 'bug_fare_scanner.py'),
         '--cities', city_key,
         '--output', out_file],
        cwd=BASE_DIR, timeout=600,
    )
    if result.returncode != 0:
        print(f"  [{ts()}] Retry FAILED for {city_name}")
        return None
    if not os.path.exists(out_file):
        return None
    with open(out_file, encoding='utf-8') as f:
        data = json.load(f)
    count = len(data.get('destinations', []))
    print(f"  [{ts()}] Retry result: {count} fares for {city_name}")
    return data

def merge_retry_into_scanner(scanner_data, retry_data, city_name):
    """Replace a city's results in scanner_data with retry_data."""
    dests = scanner_data.get('destinations', [])
    # Remove old results for this city
    dests = [d for d in dests if d.get('origin_city') != city_name]
    # Add retry results
    dests.extend(retry_data.get('destinations', []))
    scanner_data['destinations'] = dests
    return scanner_data

def run_monitor(check_only=False, force_retry=False):
    print(f"\n{'='*65}")
    print(f"  PIPELINE MONITOR — {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"{'='*65}")

    # --- Check scanner results ---
    scanner_data = load_scanner()
    if not scanner_data:
        print("  CRITICAL: scanner_results.json not found!")
        return False

    baseline = load_baseline()
    problems, counts = check_scanner(scanner_data, baseline)
    total = len(scanner_data.get('destinations', []))
    print(f"\n  Scanner: {total} total fares across {len(counts)} cities")

    if baseline:
        print(f"  Baseline: {sum(baseline.values())} fares from last archived run")

    if not problems:
        print("  ✓ All cities look healthy")
    else:
        criticals = [p for p in problems if p['severity'] == 'CRITICAL']
        warnings  = [p for p in problems if p['severity'] == 'WARNING']
        print(f"\n  Issues found: {len(criticals)} critical, {len(warnings)} warnings")
        for p in problems:
            icon = '✗' if p['severity'] == 'CRITICAL' else '⚠'
            print(f"  {icon} {p['city']:20s} {p['count']:3d} fares — {p['reason']}")

    # --- Check verify results ---
    verify_data = load_verify()
    if verify_data:
        verify_issues = check_verify(verify_data)
        results = verify_data.get('results', [])
        bookable = [r for r in results if r.get('has_booking_page')]
        print(f"\n  Verify: {len(bookable)}/{len(results)} bookable "
              f"({len(bookable)/len(results):.0%})" if results else "\n  Verify: no results")
        if not verify_issues:
            print("  ✓ Verify results look healthy")
        for vi in verify_issues:
            print(f"  ⚠ {vi['reason']}")
    else:
        print("\n  Verify: no file yet")

    if check_only:
        print(f"\n{'='*65}")
        return len([p for p in problems if p['severity'] == 'CRITICAL']) == 0

    # --- Auto-retry critical cities ---
    cities_to_retry = []
    if force_retry:
        cities_to_retry = list(counts.keys())
    else:
        cities_to_retry = [p['city'] for p in problems if p['severity'] == 'CRITICAL']

    if not cities_to_retry:
        print(f"\n  No retries needed.")
        print(f"{'='*65}")
        return True

    print(f"\n  Auto-retrying {len(cities_to_retry)} cities: {', '.join(cities_to_retry)}")
    fixed = []
    still_broken = []

    for city in cities_to_retry:
        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            retry_data = retry_city(city, attempt)
            if retry_data and len(retry_data.get('destinations', [])) >= MIN_FARES_PER_CITY:
                scanner_data = merge_retry_into_scanner(scanner_data, retry_data, city)
                fixed.append(city)
                success = True
                break
        if not success:
            still_broken.append(city)

    # Save updated scanner results if any cities were fixed
    if fixed:
        with open(SCANNER_FILE, 'w', encoding='utf-8') as f:
            json.dump(scanner_data, f, indent=2, ensure_ascii=False)
        print(f"\n  ✓ Fixed and merged: {', '.join(fixed)}")
        print(f"  Updated scanner_results.json: "
              f"{len(scanner_data.get('destinations',[]))} total fares")

    if still_broken:
        print(f"\n  ✗ Still failing after {MAX_RETRIES} attempts: {', '.join(still_broken)}")
        print(f"    These cities may need manual investigation.")

    all_ok = len(still_broken) == 0
    print(f"\n{'='*65}")
    print(f"  Monitor result: {'PASS' if all_ok else 'PARTIAL — some cities could not be recovered'}")
    print(f"{'='*65}")
    return all_ok


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--force-retry', action='store_true')
    args = parser.parse_args()
    ok = run_monitor(check_only=args.check_only, force_retry=args.force_retry)
    sys.exit(0 if ok else 1)
