"""
Railway Entrypoint

Runs when the cron fires on Railway. Handles:
- Redirecting all data paths to /data (Railway persistent volume)
- Running the full pipeline
- Auto-pushing updated HTML to GitHub for GitHub Pages hosting
- Exit 0 on success, exit 1 on failure (triggers Railway restart policy)
"""
import sys, os, subprocess, shutil, time
from datetime import datetime, timezone, timedelta

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SHANGHAI_TZ = timezone(timedelta(hours=8))
APP_DIR  = '/app'
DATA_DIR = os.environ.get('RAILWAY_DATA_DIR', '/data')
PYTHON   = sys.executable

# GitHub config for auto-push
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO  = os.environ.get('GITHUB_REPO', 'enzymesbio/claudecodeflightdeals')
GITHUB_EMAIL = os.environ.get('GITHUB_EMAIL', 'scanner@bugfare.local')
GITHUB_NAME  = os.environ.get('GITHUB_NAME', 'Bug Fare Scanner')


def ts():
    return datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M:%S Shanghai')


def symlink_data_paths():
    """Point all data files to /data volume so they persist across deploys.
    If DATA_DIR == APP_DIR or /data is not a real mount, skip symlinking."""
    # If data dir is same as app, or /data is not a real mounted volume, skip symlinks
    if DATA_DIR == APP_DIR or not os.path.ismount(DATA_DIR):
        # Just ensure logs and archive dirs exist in /app
        os.makedirs(os.path.join(APP_DIR, 'archive'), exist_ok=True)
        os.makedirs(os.path.join(APP_DIR, 'logs'), exist_ok=True)
        print(f"[{ts()}] No volume mount detected — using {APP_DIR} for data (ephemeral)")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, 'archive'), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, 'logs'), exist_ok=True)

    data_files = [
        'scanner_results.json',
        'deep_verify_all_results.json',
        'oneway_results.json',
        'drill_results.json',
        'trend_lookup.json',
        'bug_fare_verify.html',
        'index.html',
    ]
    for fname in data_files:
        app_path  = os.path.join(APP_DIR, fname)
        data_path = os.path.join(DATA_DIR, fname)
        # Remove existing file/symlink in app dir
        if os.path.exists(app_path) or os.path.islink(app_path):
            os.remove(app_path)
        # Create symlink: /app/foo.json -> /data/foo.json
        os.symlink(data_path, app_path)

    # Symlink archive and logs dirs
    for dname in ('archive', 'logs'):
        app_path  = os.path.join(APP_DIR, dname)
        data_path = os.path.join(DATA_DIR, dname)
        if os.path.exists(app_path) and not os.path.islink(app_path):
            shutil.rmtree(app_path)
        elif os.path.islink(app_path):
            os.remove(app_path)
        if not os.path.islink(app_path):
            os.symlink(data_path, app_path)

    print(f"[{ts()}] Data paths linked to {DATA_DIR}")


def run_pipeline():
    """Run the full pipeline."""
    print(f"[{ts()}] Starting full pipeline...")
    result = subprocess.run(
        [PYTHON, os.path.join(APP_DIR, 'run_full_pipeline.py')],
        cwd=APP_DIR,
        timeout=10800,  # 3 hour max
    )
    return result.returncode == 0


def push_to_github():
    """Push updated HTML files to GitHub so GitHub Pages reflects latest results."""
    if not GITHUB_TOKEN:
        print(f"[{ts()}] No GITHUB_TOKEN — skipping GitHub push")
        return

    repo_url = f'https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git'
    work_dir = '/tmp/gh_push'

    try:
        # Clean work dir
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)

        # Clone repo (shallow)
        subprocess.run(['git', 'clone', '--depth=1', repo_url, work_dir],
                       check=True, timeout=120)

        # Copy updated files
        files_to_push = [
            ('bug_fare_verify.html', 'bug_fare_verify.html'),
            ('index.html',           'index.html'),
        ]
        changed = False
        for src_name, dst_name in files_to_push:
            src = os.path.join(DATA_DIR, src_name)
            dst = os.path.join(work_dir, dst_name)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                changed = True

        # Copy archive index
        archive_src = os.path.join(DATA_DIR, 'archive')
        archive_dst = os.path.join(work_dir, 'archive')
        if os.path.exists(archive_src):
            if os.path.exists(archive_dst):
                shutil.rmtree(archive_dst)
            shutil.copytree(archive_src, archive_dst)
            changed = True

        if not changed:
            print(f"[{ts()}] No files to push")
            return

        # Commit and push
        run_time = datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M')
        subprocess.run(['git', 'config', 'user.email', GITHUB_EMAIL], cwd=work_dir, check=True)
        subprocess.run(['git', 'config', 'user.name', GITHUB_NAME],  cwd=work_dir, check=True)
        subprocess.run(['git', 'add', '-A'], cwd=work_dir, check=True)
        result = subprocess.run(
            ['git', 'commit', '-m', f'Auto-scan results {run_time} Shanghai'],
            cwd=work_dir, capture_output=True, text=True
        )
        if result.returncode != 0 and 'nothing to commit' in result.stdout:
            print(f"[{ts()}] GitHub: nothing changed since last push")
            return
        subprocess.run(['git', 'push'], cwd=work_dir, check=True, timeout=60)
        print(f"[{ts()}] GitHub Pages updated: {GITHUB_REPO}")

    except Exception as e:
        print(f"[{ts()}] GitHub push failed: {e}")
    finally:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)


def main():
    print(f"\n{'='*60}")
    print(f"  RAILWAY BUG FARE SCANNER")
    print(f"  {ts()}")
    print(f"  Data dir: {DATA_DIR}")
    print(f"{'='*60}\n")

    # 1. Link data paths to persistent volume
    symlink_data_paths()

    # 2. Run full pipeline
    ok = run_pipeline()

    # 3. Push results to GitHub regardless of pipeline success
    push_to_github()

    print(f"\n[{ts()}] Done — {'SUCCESS' if ok else 'PIPELINE HAD ERRORS'}")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
