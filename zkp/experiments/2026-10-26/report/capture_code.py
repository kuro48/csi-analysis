#!/usr/bin/env python3
"""Save exact source excerpts as local HTML and optional Chrome PNG captures."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')


def capture(source: Path, start: int, end: int, title: str, output: Path, png: bool) -> dict:
    lines = source.read_text(encoding='utf-8').splitlines()
    if not 1 <= start <= end <= len(lines):
        raise ValueError('Invalid source line range')
    body = '\n'.join(
        f'<div class="line"><span class="number">{i}</span><span>{html.escape(lines[i-1])}</span></div>'
        for i in range(start, end + 1)
    )
    relative = source.resolve().relative_to(ROOT)
    document = f'''<!doctype html><html lang="ja"><meta charset="utf-8">
<title>{html.escape(title)}</title><style>
*{{box-sizing:border-box}} body{{margin:0;background:#101923;color:#e6edf3;padding:32px}}
h1{{font:600 26px -apple-system,sans-serif;margin:0 0 12px}}
.path{{font:16px monospace;color:#91a9c0;margin-bottom:24px}}
.code{{font:19px/1.55 Menlo,monospace}}
.line{{display:flex;white-space:pre}}.number{{color:#71869b;display:inline-block;min-width:80px;user-select:none}}
.footer{{font:14px -apple-system,sans-serif;color:#91a9c0;margin-top:22px}}
</style><h1>{html.escape(title)}</h1><div class="path">{relative}:{start}–{end}</div>
<div class="code">{body}</div><div class="footer">2026-10-26 実験コード • 元ファイルからの抜粋</div></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding='utf-8')
    result = {'source': str(relative), 'start': start, 'end': end,
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'html': str(output)}
    if png:
        height = max(500, (end - start + 1) * 30 + 185)
        target = output.with_suffix('.png').resolve()
        with tempfile.TemporaryDirectory(prefix='csi-report-chrome-') as profile:
            subprocess.run([str(CHROME), '--headless', '--disable-gpu', '--no-first-run',
                            '--no-default-browser-check', f'--user-data-dir={profile}',
                            '--hide-scrollbars', f'--window-size=1500,{height}',
                            f'--screenshot={target}', output.resolve().as_uri()],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           timeout=60)
        result['png'] = str(target)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('start', type=int)
    parser.add_argument('end', type=int)
    parser.add_argument('--title', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--png', action='store_true')
    args = parser.parse_args()
    result = capture(args.source, args.start, args.end, args.title, args.output, args.png)
    args.output.with_suffix('.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False))
