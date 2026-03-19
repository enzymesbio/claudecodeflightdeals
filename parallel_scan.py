"""Launch parallel scans - 1 browser per city, merge results."""
import subprocess
import sys
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

CITIES = [
    'jakarta', 'kuala_lumpur', 'bangkok', 'singapore', 'manila',
    'ho_chi_minh', 'hong_kong', 'taipei', 'seoul', 'tokyo',
    'shanghai', 'hangzhou', 'ningbo', 'nanjing', 'beijing',
    'qingdao', 'dalian', 'wuhan', 'guangzhou', 'chengdu',
    'chongqing', 'shenzhen',
]

CABINS = '1,2,3,4'
BASE_DIR = 'D:/claude/flights'

def scan_city(city):
    """Run scanner for a single city, return output file path."""
    out_file = os.path.join(BASE_DIR, f'scan_{city}.json')
    cmd = [
        sys.executable, os.path.join(BASE_DIR, 'bug_fare_scanner.py'),
        '--cities', city,
        '--cabins', CABINS,
        '--output', out_file,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                encoding='utf-8', errors='replace')
        if os.path.exists(out_file):
            with open(out_file, encoding='utf-8') as f:
                data = json.load(f)
            bugs = data['summary']['total_bug_fares']
            dests = data['summary']['total_destinations_found']
            cheap = data['summary']['total_cheap_fares']
            tag = ' *** BUG FARES ***' if bugs > 0 else ''
            print(f"  {city:20s} | {dests:3d} dests | {bugs:2d} bugs | {cheap:2d} cheap{tag}", flush=True)
            return out_file
        else:
            print(f"  {city:20s} | FAILED - no output file", flush=True)
            if result.stderr:
                print(f"    stderr: {result.stderr[:200]}", flush=True)
            return None
    except subprocess.TimeoutExpired:
        print(f"  {city:20s} | TIMEOUT (5 min)", flush=True)
        return None
    except Exception as e:
        print(f"  {city:20s} | ERROR: {e}", flush=True)
        return None


def merge_results(scan_files, output='scanner_results_merged.json'):
    """Merge multiple scan result JSON files into one."""
    all_destinations = []
    all_cities = []
    all_cabins = set()

    for sf in scan_files:
        if not sf or not os.path.exists(sf):
            continue
        with open(sf, encoding='utf-8') as f:
            data = json.load(f)
        all_destinations.extend(data.get('destinations', []))
        all_cities.extend(data.get('cities_scanned', []))
        for c in data.get('cabins_scanned', []):
            all_cabins.add(c)

    # Classify
    bug_fares = [d for d in all_destinations if d.get('classification') == 'BUG_FARE']
    cheap_fares = [d for d in all_destinations if d.get('classification') == 'CHEAP']

    merged = {
        'scan_timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'cities_scanned': sorted(set(all_cities)),
        'cabins_scanned': sorted(all_cabins),
        'summary': {
            'total_destinations_found': len(all_destinations),
            'total_bug_fares': len(bug_fares),
            'total_cheap_fares': len(cheap_fares),
        },
        'destinations': all_destinations,
        'bug_fares': bug_fares,
        'cheap_fares': cheap_fares,
    }

    out_path = os.path.join(BASE_DIR, output)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"\nMerged: {len(all_destinations)} destinations from {len(all_cities)} cities")
    print(f"Bug fares: {len(bug_fares)}, Cheap: {len(cheap_fares)}")
    print(f"Saved to: {out_path}")
    return out_path


if __name__ == '__main__':
    cities = sys.argv[1:] if len(sys.argv) > 1 else CITIES
    max_workers = len(cities)  # 1 browser per city

    print(f"{'='*60}")
    print(f"  PARALLEL SCAN: {len(cities)} cities x 4 cabins")
    print(f"  Max workers: {max_workers}")
    print(f"{'='*60}\n")

    start = time.time()
    scan_files = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_city, city): city for city in cities}
        for future in as_completed(futures):
            result = future.result()
            if result:
                scan_files.append(result)

    elapsed = time.time() - start
    print(f"\nAll scans done in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Successful: {len(scan_files)}/{len(cities)}")

    if scan_files:
        merged_path = merge_results(scan_files)
        # Also copy to scanner_results.json for the HTML generator
        import shutil
        shutil.copy2(merged_path, os.path.join(BASE_DIR, 'scanner_results.json'))
        print(f"Copied to scanner_results.json")
