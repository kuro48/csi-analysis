#!/usr/bin/env python3
"""Render and check two bookmarked views of the verified public-output viewer."""
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
cases = [
    ('trace_vmd', 'VMD', '各反復のモード波形', '反復 4'),
    ('trace_lomb', 'Lomb–Scargle', 'LSスコア', 'SC 7（回路が選択）'),
]
results = []
for name, method, stage, choice in cases:
    url = (HERE / 'trace_viewer.html').as_uri() + '?' + urlencode(
        dict(method=method, stage=stage, choice=choice))
    with tempfile.TemporaryDirectory(prefix='csi-trace-chrome-') as profile:
        result = subprocess.run([
            CHROME, '--headless', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--hide-scrollbars', '--window-size=1400,1100',
            f'--user-data-dir={profile}', '--virtual-time-budget=2000', '--dump-dom',
            f'--screenshot={HERE / (name + ".png")}', url,
        ], check=True, capture_output=True, text=True, timeout=60)
    assert 'data-rendered="true"' in result.stdout
    assert f'data-current-stage="{stage}"' in result.stdout
    assert f'data-current-choice="{choice}"' in result.stdout
    results.append(dict(view=name, method=method, stage=stage, choice=choice, rendered=True))
(HERE / 'trace_render_validation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(results, ensure_ascii=False, indent=2))
