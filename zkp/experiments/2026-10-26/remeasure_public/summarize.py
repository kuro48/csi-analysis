"""Summarize only remeasured proof outputs; keep independent records and repeats separate."""
import csv,html,json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
view=json.loads((HERE/'viewer_validation.json').read_text());runs=view['runs']
with (BASE/'vmd/raw_only/sweep.csv').open() as f:vmd={r['case']:float(r['ls_band_bpm']) for r in csv.DictReader(f) if r['kind']=='real'}
with (BASE/'lomb/accuracy.csv').open() as f:ls={r['window_id']:float(r['float_all_sc_bpm']) for r in csv.DictReader(f)}
rows=[]
for cfg in view['configuration_status']:
    rr=[r for r in runs if r['method']==cfg['method'] and r['config']==cfg['config']]
    unique=[r for r in rr if r['repeat']==0];reps=[r for r in rr if r['window']=='csi_20260526_034004_w0']
    ref=vmd if cfg['method']=='VMD' else ls
    for r in unique:r['reference_bpm']=ref[r['window']];r['absolute_difference_bpm']=abs(r['bpm']-ref[r['window']])
    rows.append(dict(method=cfg['method'],config=cfg['config'],status=cfg['status'],proofs=len(rr),raw_windows=len(unique),timing_repeats=len(reps),
       prove_seconds_median=statistics.median(r['seconds'] for r in reps) if len(reps)==3 else None,
       mean_absolute_difference_bpm=statistics.mean(r['absolute_difference_bpm'] for r in unique) if len(unique)==8 else None))
(HERE/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
with (HERE/'results.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (HERE/'individual_proof_results.csv').open('w',newline='') as f:
    keys=['id','method','config','window','repeat','bpm','seconds','public_sha256','proof_sha256'];w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(runs)
def fmt(v):return '—' if v is None else (f'{v:.3f}' if isinstance(v,float) else str(v))
body=''.join('<tr>'+''.join('<td>'+html.escape(fmt(r[k]))+'</td>' for k in ['method','config','status','proofs','raw_windows','timing_repeats','prove_seconds_median','mean_absolute_difference_bpm'])+'</tr>' for r in rows)
complete=sum(r['proofs']==10 and r['raw_windows']==8 and r['timing_repeats']==3 for r in rows)
doc=f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>公開中間値を含む比較回路の再測定</title><style>body{{font:17px/1.8 -apple-system,"Hiragino Sans",sans-serif;color:#234;margin:40px auto;max-width:1250px;padding:0 24px}}h1{{font-size:29px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #d7dfe5}}th{{background:#edf3f7}}a{{color:#176a96}}.note{{padding:15px;background:#fff5e8}}</style><h1>公開中間値を含む比較回路での再測定</h1>
<p><strong>掲載時点：{len(runs)}証明が検証済み、{complete}/43構成で各10証明が完了。</strong></p>
<p>各構成の回路自体から中間値を公開し、<a href="index.html">その証明のpublic.jsonで波形を表示</a>。以前の別診断実行の波形・時間は、この表には含めていません。</p>
<p class="note">一致度は実8収録、時間は同じ代表収録の3回中央値。各条件が揃うまで集計値は「—」とし、未実行・失敗を0扱いしません。VMDの参照は同じ入力PCA波形のLS、LSの参照は同じアンテナ対の全サブキャリアLS。正解呼吸数への誤差ではありません。端末はM4 Pro/RAM24GiB。</p>
<table><thead><tr><th>方式</th><th>設定</th><th>状態</th><th>proof /10</th><th>収録 /8</th><th>計時 /3</th><th>prove中央値(s)</th><th>LS参照との差(BPM)</th></tr></thead><tbody>{body}</tbody></table>
<p><a href="results.csv">構成別CSV</a> / <a href="individual_proof_results.csv">各proofの出力と時間</a> / <a href="README.md">条件と証明範囲</a></p></html>'''
(HERE/'report.html').write_text(doc)
print(f'{complete}/43 configs, {len(runs)} verified proofs')
