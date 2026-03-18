"""
Archive Run — saves current scan results to timestamped archive folder,
compares with previous runs, generates trend summary and updates main index.

Usage:
    python archive_run.py           # archive latest results + regenerate index
    python archive_run.py --compare # just show comparison without archiving
"""
import sys, os, json, re, argparse, shutil
from datetime import datetime, timezone, timedelta
from collections import defaultdict

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR   = 'D:/claude/flights'
ARCHIVE_DIR = os.path.join(BASE_DIR, 'archive')
INDEX_FILE  = os.path.join(BASE_DIR, 'index.html')
SHANGHAI_TZ = timezone(timedelta(hours=8))

FAMILY_MULT = 2.75
FAMILY_BUDGET = 2000  # USD

# Files to archive per run
ARCHIVE_FILES = [
    'scanner_results.json',
    'deep_verify_all_results.json',
    'oneway_results.json',
    'drill_results.json',
    'bug_fare_verify.html',
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_str():
    return datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')

def load_runs():
    """Return list of archived run metadata, newest first."""
    runs = []
    if not os.path.exists(ARCHIVE_DIR):
        return runs
    for entry in sorted(os.scandir(ARCHIVE_DIR), key=lambda e: e.name, reverse=True):
        if entry.is_dir():
            meta_path = os.path.join(entry.path, 'meta.json')
            if os.path.exists(meta_path):
                with open(meta_path, encoding='utf-8') as f:
                    meta = json.load(f)
                meta['dir'] = entry.path
                meta['slug'] = entry.name
                runs.append(meta)
    return runs

def load_scanner(path):
    """Load scanner_results.json and return affordable fares list."""
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return [d for d in data.get('destinations', [])
            if d['price_usd'] * FAMILY_MULT <= FAMILY_BUDGET
            and d.get('origin_city') != 'Taipei']

def load_verify(path):
    """Load deep_verify_all_results.json, return bookable results."""
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return [r for r in data.get('results', []) if r.get('has_booking_page')]

def fare_key(f):
    """Stable key for tracking a route across runs."""
    return (f.get('origin_city', ''), f.get('destination', ''), f.get('cabin', 'Economy'))

def verify_key(r):
    return (r.get('origin', ''), r.get('city', ''), r.get('cabin', 'Economy'))

# ---------------------------------------------------------------------------
# Comparison engine
# ---------------------------------------------------------------------------

def compare_runs(current_fares, prev_fares):
    """Compare two fare lists. Returns dict of changes."""
    curr = {fare_key(f): f for f in current_fares}
    prev = {fare_key(f): f for f in prev_fares}

    new_routes   = []  # in curr but not prev
    gone_routes  = []  # in prev but not curr
    cheaper      = []  # price dropped
    pricier      = []  # price increased
    stable       = []  # within 5%

    for key, f in curr.items():
        if key not in prev:
            new_routes.append(f)
        else:
            p_old = prev[key]['price_usd']
            p_new = f['price_usd']
            delta_pct = (p_new - p_old) / p_old * 100
            entry = {**f, 'prev_price': p_old, 'delta_pct': delta_pct}
            if delta_pct < -5:
                cheaper.append(entry)
            elif delta_pct > 5:
                pricier.append(entry)
            else:
                stable.append(entry)

    for key, f in prev.items():
        if key not in curr:
            gone_routes.append(f)

    return {
        'new_routes':  sorted(new_routes, key=lambda x: x['price_usd']),
        'gone_routes': sorted(gone_routes, key=lambda x: x['price_usd']),
        'cheaper':     sorted(cheaper, key=lambda x: x['delta_pct']),
        'pricier':     sorted(pricier, key=lambda x: x['delta_pct'], reverse=True),
        'stable':      sorted(stable, key=lambda x: x['price_usd']),
    }


def ai_trend_summary(comparison, run_meta, prev_meta):
    """Generate a concise plain-text + HTML trend analysis."""
    c = comparison
    total_new    = len(c['new_routes'])
    total_gone   = len(c['gone_routes'])
    total_cheaper = len(c['cheaper'])
    total_pricier = len(c['pricier'])

    lines = []
    run_date  = run_meta.get('scan_time', '')[:10]
    prev_date = prev_meta.get('scan_time', '')[:10] if prev_meta else 'N/A'

    lines.append(f"Comparing {run_date} vs {prev_date}:")

    if total_new:
        lines.append(f"  +{total_new} new affordable route{'s' if total_new>1 else ''}:")
        for f in c['new_routes'][:5]:
            fam = round(f['price_usd'] * FAMILY_MULT)
            lines.append(f"    NEW  {f['origin_city']} → {f['destination']}  ${f['price_usd']}/pp (${fam} fam)")

    if total_cheaper:
        lines.append(f"  ↓ {total_cheaper} route{'s' if total_cheaper>1 else ''} got cheaper:")
        for f in c['cheaper'][:5]:
            lines.append(f"    ↓    {f['origin_city']} → {f['destination']}  "
                         f"${f['prev_price']}→${f['price_usd']}/pp ({f['delta_pct']:+.0f}%)")

    if total_pricier:
        lines.append(f"  ↑ {total_pricier} route{'s' if total_pricier>1 else ''} got more expensive:")
        for f in c['pricier'][:5]:
            lines.append(f"    ↑    {f['origin_city']} → {f['destination']}  "
                         f"${f['prev_price']}→${f['price_usd']}/pp ({f['delta_pct']:+.0f}%)")

    if total_gone:
        lines.append(f"  -{total_gone} route{'s' if total_gone>1 else ''} disappeared (above budget or gone):")
        for f in c['gone_routes'][:5]:
            lines.append(f"    GONE {f['origin_city']} → {f['destination']}  was ${f['price_usd']}/pp")

    if not any([total_new, total_gone, total_cheaper, total_pricier]):
        lines.append("  No significant changes since last run.")

    return '\n'.join(lines)


def trend_badge(delta_pct):
    if delta_pct < -10:
        return '<span class="badge badge-drop">↓↓ BIG DROP</span>'
    elif delta_pct < -3:
        return '<span class="badge badge-drop">↓ Cheaper</span>'
    elif delta_pct > 10:
        return '<span class="badge badge-rise">↑↑ Big Rise</span>'
    elif delta_pct > 3:
        return '<span class="badge badge-rise">↑ Pricier</span>'
    else:
        return '<span class="badge badge-stable">= Stable</span>'


def build_trend_html(comparison, prev_date):
    """Build a concise HTML comparison table for embedding in the index."""
    c = comparison
    sections = []

    def fare_row(f, row_cls='', extra=''):
        fam = round(f['price_usd'] * FAMILY_MULT)
        prev = f.get('prev_price', '')
        delta = f.get('delta_pct', None)
        prev_cell = f'<span style="color:#718096;text-decoration:line-through">${prev}</span> → ' if prev else ''
        delta_cell = trend_badge(delta) if delta is not None else ''
        return (f'<tr class="{row_cls}">'
                f'<td>{f["origin_city"]}</td><td>{f["destination"]}</td>'
                f'<td>{f.get("cabin","Economy")}</td>'
                f'<td>{prev_cell}<strong>${f["price_usd"]}</strong>/pp&nbsp;'
                f'<span style="color:#718096">(${fam} fam)</span></td>'
                f'<td>{delta_cell}{extra}</td>'
                f'<td style="color:#718096;font-size:11px">{f.get("dates","")}</td>'
                f'</tr>')

    thead = ('<table class="diff-table"><thead><tr>'
             '<th>Origin</th><th>Dest</th><th>Cabin</th>'
             '<th>Price</th><th>Trend</th><th>Dates</th>'
             '</tr></thead><tbody>')
    tfoot = '</tbody></table>'

    if c['new_routes']:
        rows = ''.join(fare_row(f, 'new-row',
                                '<span class="badge badge-new">NEW</span>')
                       for f in c['new_routes'][:8])
        sections.append(f'<div class="diff-section"><h4>✦ New routes ({len(c["new_routes"])})</h4>'
                        f'{thead}{rows}{tfoot}</div>')

    if c['cheaper']:
        rows = ''.join(fare_row(f, 'cheap-row') for f in c['cheaper'][:8])
        sections.append(f'<div class="diff-section"><h4>↓ Got cheaper ({len(c["cheaper"])})</h4>'
                        f'{thead}{rows}{tfoot}</div>')

    if c['pricier']:
        rows = ''.join(fare_row(f, 'pricey-row') for f in c['pricier'][:6])
        sections.append(f'<div class="diff-section"><h4>↑ Got more expensive ({len(c["pricier"])})</h4>'
                        f'{thead}{rows}{tfoot}</div>')

    if c['gone_routes']:
        rows = ''.join(fare_row(f, 'gone-row',
                                '<span class="badge badge-rise">GONE</span>')
                       for f in c['gone_routes'][:6])
        sections.append(f'<div class="diff-section"><h4>✕ Disappeared ({len(c["gone_routes"])})</h4>'
                        f'{thead}{rows}{tfoot}</div>')

    if not sections:
        return '<p style="color:#718096;font-size:13px">No significant changes vs previous run.</p>'

    header = (f'<p style="color:#718096;font-size:12px;margin:0 0 8px">'
              f'vs {prev_date}</p>')
    return header + ''.join(sections)


def build_trend_lookup(comparison):
    """Return dict: fare_key → delta_pct for embedding in fare table rows."""
    lookup = {}
    for f in comparison.get('cheaper', []):
        lookup[fare_key(f)] = f['delta_pct']
    for f in comparison.get('pricier', []):
        lookup[fare_key(f)] = f['delta_pct']
    for f in comparison.get('new_routes', []):
        lookup[fare_key(f)] = None  # None = new
    for f in comparison.get('gone_routes', []):
        lookup[fare_key(f)] = 999   # 999 = gone sentinel
    return lookup

# ---------------------------------------------------------------------------
# HTML index generator
# ---------------------------------------------------------------------------

def generate_index(runs):
    """Generate archive/index.html listing all runs with comparison summaries."""
    now = now_str()

    style = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background:#0f1117; color:#e2e8f0; margin:0; padding:0; }
.header { background:#1a202c; padding:24px 32px; border-bottom:2px solid #276749; }
.header h1 { margin:0; font-size:24px; color:#68d391; }
.header .sub { color:#718096; font-size:13px; margin-top:4px; }
.container { max-width:1200px; margin:0 auto; padding:24px 32px; }
.run-card { background:#1a202c; border:1px solid #2d3748; border-radius:8px;
            margin-bottom:20px; overflow:hidden; }
.run-card.latest { border-color:#276749; }
.run-header { padding:16px 20px; background:#2d3748; display:flex;
              align-items:center; gap:16px; flex-wrap:wrap; }
.run-title { font-size:16px; font-weight:700; color:#e2e8f0; }
.run-date { font-size:12px; color:#718096; }
.run-body { padding:16px 20px; }
.stats { display:flex; gap:20px; flex-wrap:wrap; margin-bottom:12px; }
.stat { text-align:center; }
.stat-val { font-size:22px; font-weight:700; color:#68d391; }
.stat-lbl { font-size:11px; color:#718096; }
.diff-section { margin-top:12px; }
.diff-section h4 { margin:0 0 6px; font-size:12px; text-transform:uppercase;
                   letter-spacing:.05em; color:#a0aec0; }
.diff-table { width:100%; border-collapse:collapse; font-size:12px; }
.diff-table td, .diff-table th { padding:4px 8px; border-bottom:1px solid #2d3748; }
.diff-table th { color:#718096; font-weight:600; text-align:left; }
.new-row td { color:#68d391; }
.gone-row td { color:#fc8181; text-decoration:line-through; }
.cheap-row td:nth-child(4) { color:#68d391; font-weight:700; }
.pricey-row td:nth-child(4) { color:#fc8181; font-weight:700; }
.badge { display:inline-block; border-radius:4px; padding:2px 6px; font-size:10px;
         font-weight:700; }
.badge-drop { background:#22543d; color:#9ae6b4; }
.badge-rise { background:#742a2a; color:#feb2b2; }
.badge-stable { background:#2d3748; color:#a0aec0; }
.badge-new  { background:#1a365d; color:#90cdf4; }
.view-btn { display:inline-block; background:#276749; color:#fff; padding:6px 14px;
            border-radius:5px; text-decoration:none; font-size:12px; font-weight:600;
            margin-top:8px; }
.view-btn:hover { background:#2f855a; }
pre.trend { background:#0f1117; border-radius:6px; padding:12px; font-size:11px;
            color:#a0aec0; overflow-x:auto; margin:8px 0 0; white-space:pre-wrap; }
</style>
"""

    cards = ''
    for i, run in enumerate(runs):
        is_latest = (i == 0)
        slug = run['slug']
        run_date = run.get('scan_time', slug)[:16].replace('T', ' ')
        affordable = run.get('affordable_count', 0)
        bookable   = run.get('bookable_count', 0)
        oneway     = run.get('oneway_count', 0)
        trend_html = run.get('trend_html', '')
        trend_text = run.get('trend_text', '')

        html_path = f'archive/{slug}/bug_fare_verify.html'
        view_link = f'<a href="{html_path}" class="view-btn">View Full Results</a>'

        latest_badge = '<span class="badge badge-new" style="background:#276749">★ LATEST</span> ' if is_latest else ''

        stats_html = f"""
<div class="stats">
  <div class="stat"><div class="stat-val">{affordable}</div><div class="stat-lbl">Affordable Fares</div></div>
  <div class="stat"><div class="stat-val">{bookable}</div><div class="stat-lbl">Bookable</div></div>
  <div class="stat"><div class="stat-val">{oneway}</div><div class="stat-lbl">One-Way Found</div></div>
</div>"""

        trend_section = ''
        if trend_text:
            trend_section = f'<pre class="trend">{trend_text}</pre>'

        cards += f"""
<div class="run-card {'latest' if is_latest else ''}">
  <div class="run-header">
    <div>
      <div class="run-title">{latest_badge}Run {run_date}</div>
      <div class="run-date">{slug}</div>
    </div>
    {view_link}
  </div>
  <div class="run-body">
    {stats_html}
    {trend_section}
  </div>
</div>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bug Fare Archive — All Runs</title>
{style}
</head>
<body>
<div class="header">
  <h1>Bug Fare Archive</h1>
  <div class="sub">All scan runs — password: <strong>bugfare2026</strong> &nbsp;|&nbsp; Updated: {now}</div>
</div>
<div class="container">
{cards}
</div>
</body>
</html>"""
    return html

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compare', action='store_true', help='Compare only, no archive')
    args = parser.parse_args()

    now = datetime.now(SHANGHAI_TZ)
    slug = now.strftime('%Y%m%d_%H%M')

    # Load current results
    scanner_path = os.path.join(BASE_DIR, 'scanner_results.json')
    verify_path  = os.path.join(BASE_DIR, 'deep_verify_all_results.json')
    oneway_path  = os.path.join(BASE_DIR, 'oneway_results.json')

    current_fares    = load_scanner(scanner_path)
    current_bookable = load_verify(verify_path)

    oneway_count = 0
    if os.path.exists(oneway_path):
        with open(oneway_path, encoding='utf-8') as f:
            oneway_data = json.load(f)
        oneway_count = oneway_data.get('total_fares', 0)

    # Load scan timestamp
    scan_time = now.isoformat()
    if os.path.exists(scanner_path):
        with open(scanner_path, encoding='utf-8') as f:
            sr = json.load(f)
        scan_time = sr.get('scan_time', scan_time)

    # Load previous runs
    existing_runs = load_runs()

    # Compare with most recent previous run
    comparison = None
    trend_text = ''
    trend_html = ''
    prev_meta  = None

    if existing_runs:
        prev_meta = existing_runs[0]
        prev_scanner = os.path.join(prev_meta['dir'], 'scanner_results.json')
        prev_fares = load_scanner(prev_scanner)
        if prev_fares:
            comparison = compare_runs(current_fares, prev_fares)
            trend_text = ai_trend_summary(comparison,
                                          {'scan_time': scan_time},
                                          prev_meta)
            prev_date = prev_meta.get('scan_time', '')[:10]
            trend_html = build_trend_html(comparison, prev_date)
            # Save trend lookup for generate_verification_page.py
            trend_lookup = build_trend_lookup(comparison)
            trend_lookup_path = os.path.join(BASE_DIR, 'trend_lookup.json')
            # Convert tuple keys to strings for JSON serialisation
            with open(trend_lookup_path, 'w', encoding='utf-8') as f:
                json.dump({'prev_date': prev_date,
                           'lookup': {'|'.join(k): v for k, v in trend_lookup.items()}},
                          f, indent=2, ensure_ascii=False)
            print(trend_text)

    if args.compare:
        return

    # --- Archive current run ---
    run_dir = os.path.join(ARCHIVE_DIR, slug)
    os.makedirs(run_dir, exist_ok=True)

    for fname in ARCHIVE_FILES:
        src = os.path.join(BASE_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(run_dir, fname))
            print(f"  Archived: {fname}")

    # Save metadata
    meta = {
        'scan_time':       scan_time,
        'slug':            slug,
        'affordable_count': len(current_fares),
        'bookable_count':  len(current_bookable),
        'oneway_count':    oneway_count,
        'trend_text':      trend_text,
        'trend_html':      trend_html,
    }
    with open(os.path.join(run_dir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # Update index
    all_runs = load_runs()  # re-load to include this run
    index_html = generate_index(all_runs)
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(index_html)
    print(f"\nArchived run: {slug}")
    print(f"Index: {INDEX_FILE} ({len(all_runs)} runs total)")


if __name__ == '__main__':
    main()
