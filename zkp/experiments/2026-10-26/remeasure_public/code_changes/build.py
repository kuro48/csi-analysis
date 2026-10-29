# -*- coding: utf-8 -*-
"""Exact current-source excerpts with line numbers; render PNG only between measurements."""
import argparse,hashlib,html,json,math,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;BASE=HERE.parent;ROOT=HERE.parents[4]
p=argparse.ArgumentParser();p.add_argument('--png',action='store_true');args=p.parse_args()
items=[
 ('01_vmd_outputs','VMD：中間値を公開出力へ追加','vmd/k3_r4/vmd_k3_r4_public.circom','signal output debugWaveform',6,'入力・DFT・反復ごとのモード係数・中心を公開配列として宣言。'),
 ('02_vmd_bindings','VMD：内部信号と公開出力を制約で接続','vmd/k3_r4/vmd_k3_r4_public.circom','for(var dt=0',7,'<==で内部計算値と公開値を結び付ける。外部で計算した別の値を公開する実装ではない。'),
 ('03_ls_bindings','LS：各サブキャリアの処理値を公開','lomb/configs/sc1/circuit.circom','    // Every stage below',10,'比較回路自身からI/Q・振幅二乗・平均除去後の値を出力。SC1は実際に証明検証済みの構成。'),
 ('04_same_proof','各実行で生成したproofとpublicを検証・読取','lomb/run.py','            m["timings"]["prove_seconds"]',18,'このrunのproveが書いたpublic.jsonをverifyし、その同じJSONを復号する。'),
 ('05_trace_binding','波形データに同じpublicの対応情報を保存','lomb/run.py','            provenance = {',25,'run・設定・入力・鍵・proof・publicを記録。traceのdecoded_fromも当該publicを指す。'),
 ('06_vmd_inverse','VMD：公開係数を時間波形へ変換','vmd/trace.py','    def inverse(real,imag):',10,'公開値の復号後に、表示側で逆DFTする。回路内で時間波形を計算したという意味ではない。'),
]
records=[]
for name,title,path,needle,count,note in items:
 source=BASE/path;lines=source.read_text().splitlines();start=next(i for i,s in enumerate(lines) if needle in s)+1;end=start+count-1
 code=''.join(f'<div class="line"><span class="number">{n}</span><code>{html.escape(lines[n-1])}</code></div>' for n in range(start,end+1))
 shown=str(source.relative_to(ROOT));height=max(470,210+sum(max(1,math.ceil(len(lines[n-1])/124))*29 for n in range(start,end+1)))
 doc=f'''<!doctype html><html lang="ja"><meta charset="utf-8"><title>{title}</title><style>*{{box-sizing:border-box}}body{{margin:0;padding:32px;background:#101923;color:#e8edf1}}h1{{font:600 28px -apple-system,sans-serif;margin:0 0 14px}}.path{{font:15px/1.5 Menlo,monospace;color:#a2b7c7;overflow-wrap:anywhere;margin-bottom:24px}}.line{{display:grid;grid-template-columns:78px 1fr;font:18px/1.6 Menlo,monospace}}code{{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}}.number{{color:#829aac}}footer{{color:#a2b7c7;font:15px/1.6 -apple-system,sans-serif;margin-top:24px}}</style><h1>{title}</h1><div class="path">{shown}:{start}–{end}</div>{code}<footer>再測定版 / 実ファイルからの抜粋 / 行番号付き</footer></html>'''
 target=HERE/(name+'.html');target.write_text(doc)
 record=dict(title=title,note=note,source=shown,start=start,end=end,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),html=name+'.html',png=name+'.png')
 if args.png:
  with tempfile.TemporaryDirectory(prefix='same-proof-code-') as profile:
   subprocess.run(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--headless','--disable-gpu','--no-first-run','--no-default-browser-check',f'--user-data-dir={profile}','--hide-scrollbars',f'--window-size=1500,{height}',f'--screenshot={HERE/record["png"]}',target.as_uri()],check=True,capture_output=True,timeout=60)
  record['png_rendered']=True
 else:record['png_rendered']=(HERE/record['png']).exists()
 (HERE/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');records.append(record)
rows=''.join(f'<section><h2>{r["title"]}</h2><p>{r["note"]}</p><p><a href="{r["html"]}">撮影用HTMLを開く</a> · '+(f'<a href="{r["png"]}">PNG</a>' if r['png_rendered'] else 'PNGは計時の合間に生成')+f'</p><iframe src="{r["html"]}" title="{r["title"]}"></iframe></section>' for r in records)
(HERE/'index.html').write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><title>今回の変更点・コード撮影用</title><style>body{max-width:1280px;margin:36px auto;padding:0 24px;font:18px/1.8 -apple-system,"Hiragino Sans",sans-serif;color:#234}h1{font-size:30px}h2{font-size:24px}section{margin:45px 0}a{color:#176a96}iframe{width:100%;height:520px;border:0}pre{padding:20px;background:#edf3f6;white-space:pre-wrap}</style><h1>今回の変更点と、スクリーンショット用コード</h1><p>今回の変更の中心は、別実行の診断値を表示する構成から、<strong>各比較proof自身の公開値を表示する構成</strong>への切り替えです。</p><pre>各設定・各収録の比較回路\n  → 中間値を含む public.json と proof.json を生成\n  → 同じ組で verify\n  → その public.json を復号して trace.json を作成\n  → proof・publicのハッシュとともに波形を表示</pre><p>発表には02・04・05を使うと、回路への接続から同じ証明との対応まで説明できます。HTMLは元ファイル名・行番号付き。PNGはそのHTMLを描画した画像です。</p>'''+rows+'<p><a href="../index.html">各proofの波形へ</a> / <a href="../report.html">再測定の実行状況へ</a></p></html>')
(HERE/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
print(HERE/'index.html')
