#!/usr/bin/env python3
"""Render the 4:3 progress summary with a separate, disposable Chrome profile."""
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

with tempfile.TemporaryDirectory(prefix='csi-summary-chrome-') as profile:
    subprocess.run([
        CHROME, '--headless', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--hide-scrollbars', '--window-size=1200,900',
        f'--user-data-dir={profile}', f'--screenshot={HERE / "summary.png"}',
        (HERE / 'summary.html').as_uri(),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
print(HERE / 'summary.png')
