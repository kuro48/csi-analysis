# -*- coding: utf-8 -*-
"""Screenshot cards showing exact parameter-editing and generated circuit excerpts."""
import argparse
import hashlib
import html
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE = HERE.parent
records = []


def block(title, relative, needle, count, highlight=()):
    path = (BASE / relative).resolve()
    lines = path.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if needle in line)
    selected = lines[start:start + count]
    records.append(dict(source=str(path.relative_to(ROOT)), start=start + 1,
                        end=start + count, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    rows = ''.join('<div class="line' + (' focus' if any(h in line for h in highlight) else '') +
                   f'"><span>{start+i+1}</span><code>{html.escape(line)}</code></div>'
                   for i, line in enumerate(selected))
    return f'<section><h2>{title}</h2><p class="path">{html.escape(str(path.relative_to(ROOT)))}</p>{rows}</section>'


STYLE = '''*{box-sizing:border-box}body{margin:0;padding:30px 36px;background:#101923;color:#e8edf1;font:18px/1.5 -apple-system,"Hiragino Sans",sans-serif}h1{font-size:30px;margin:0 0 10px}h2{font-size:21px;margin:0 0 8px;color:#9ed9ff}.intro{color:#cfdae2;margin:8px 0 20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}section{padding:18px;background:#182532;border-radius:8px;min-width:0}.path{font:12px/1.4 Menlo,monospace;color:#a4bacb;overflow-wrap:anywhere;margin:0 0 12px}.line{display:grid;grid-template-columns:40px 1fr;font:16px/1.55 Menlo,monospace}.line span{color:#829aac}code{min-width:0;font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}.focus{background:#463d20;color:#ffdf88}footer{margin-top:18px;color:#b6c7d3;font-size:15px}'''


vmd = block('① 比較するモード数 K と反復数 R', 'vmd/generate.py', 'K_VALUES=', 2, ['K_VALUES', 'R_VALUES'])
vmd += block('② 設定値を回路生成関数へ渡す', 'vmd/generate.py', 'def generate(config):', 5, ['k,r=', 'generate_base'])
vmd += block('③ K = 3：3モード分の回路配列', 'vmd/k3_r4/vmd_k3_r4_public.circom', 'signal ur[4][3][63]', 3, ['[3]'])
vmd += block('④ K = 4：4モード分の回路配列', 'vmd/k4_r4/vmd_k4_r4_public.circom', 'signal ur[4][4][63]', 3, ['[4]'])
ls = block('① 回路のサブキャリア数を c に置換', 'lomb/schema.py', 'def source(original, c):', 6, ['marker, f'])
ls += block('② 生成された回路：第2引数が本数', 'lomb/configs/sc4/circuit.circom', 'component main', 4, ['    4,'])
ls += block('③ 入力 I/Q の列数も SUBCARRIERS', 'lomb/configs/sc4/circuit.circom', 'signal input csiI', 2, ['SUBCARRIERS'])
ls += block('④ 入力データも先頭 count 列へ切り出す', '../lomb/run.py', '        for count in COUNTS:', 8, ['r[:count]'])

pages = [
    ('07_vmd_mode_count', 'VMD：モード数をどこで変えているか',
     'K = 1, 2, 3, 4, 5, 8 を比較。下段は反復数 R = 4 を固定し、K = 3 → 4 に変えた実回路です。', vmd,
     'ur / ui は [反復数 R][モード数 K][周波数63点]、center は [R+1][K]。K ごとに回路を生成・コンパイルします。'),
    ('08_ls_subcarrier_count', 'Lomb–Scargle：入力サブキャリア数をどこで変えているか',
     '1, 2, 4, 8, 16, 32 本を比較。回路の引数と、入力 I/Q の列数を同じ本数へ変更します。', ls,
     '② は4本の実回路（引数順：サンプル数64、本数4、周波数点32）。④ は再測定で再利用する入力JSONの生成箇所。'),
]
parser = argparse.ArgumentParser()
parser.add_argument('--png', action='store_true')
args = parser.parse_args()
for name, title, intro, content, note in pages:
    target = HERE / (name + '.html')
    target.write_text(f'<!doctype html><html lang="ja"><meta charset="utf-8"><title>{title}</title><style>{STYLE}</style><h1>{title}</h1><p class="intro">{intro}</p><div class="grid">{content}</div><footer>{note}<br>実ソースの抜粋・元の行番号を表示。黄色：本数／モード数が反映される箇所。</footer></html>')
    if args.png:
        with tempfile.TemporaryDirectory(prefix='parameter-code-') as profile:
            subprocess.run(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', f'--user-data-dir={profile}', '--hide-scrollbars', '--window-size=1600,950', f'--screenshot={HERE / (name + ".png")}', target.as_uri()], check=True, capture_output=True, timeout=60)
(HERE / 'parameter_manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
index = HERE / 'index.html'
text = index.read_text()
begin, end = '<!-- parameters:start -->', '<!-- parameters:end -->'
if begin in text:
    text = text[:text.index(begin)] + text[text.index(end) + len(end):]
addition = begin + '<section><h2>モード数・入力サブキャリア数の変更箇所</h2>'
for name, title, *_ in pages:
    addition += f'<p><a href="{name}.html">{title}：撮影用HTML</a> ／ <a href="{name}.png">PNG画像</a></p>'
addition += '</section>' + end
text = text.replace('<h1>今回の変更点と、スクリーンショット用コード</h1>', '<h1>今回の変更点と、スクリーンショット用コード</h1>' + addition)
index.write_text(text)
print(index)
