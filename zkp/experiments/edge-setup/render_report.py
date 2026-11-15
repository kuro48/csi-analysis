#!/usr/bin/env python3
"""Build a screenshot-friendly, offline HTML report from actual step records."""

import datetime as dt
import html
import json
from pathlib import Path
import re
import shlex

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "2026-10-19"


def esc(value):
    return html.escape(str(value))


def strip_ansi(text):
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def evidence(text):
    """Keep actual output, omit shell tracing and curl progress in the slide excerpt."""
    lines = []
    for line in text.splitlines():
        if line.startswith(("+", "STEP ", "START ", "END ")):
            continue
        if re.match(r"\s*\d+\s+\d+[.\dA-Za-z]*\s+", line):
            continue
        if line.strip() and not line.startswith(("  % Total", "                                 Dload")):
            lines.append(line)
    return "\n".join(lines[-16:])


def main():
    steps = json.loads((ROOT / "steps.json").read_text())
    notes_path = RUN / "findings.json"
    notes = json.loads(notes_path.read_text()) if notes_path.exists() else {}
    records = [json.loads(p.read_text()) for p in sorted((RUN / "records").glob("*.json"))]
    by_id = {}
    for record in records:
        by_id.setdefault(record["id"], []).append(record)
    measurements = []
    for sid, label in (("17", "合成15 BPM"), ("20", "実CSI① 10/05 11:56"), ("21", "実CSI② 10/05 11:55"), ("22", "実CSI③ 09/07")):
        if not by_id.get(sid):
            continue
        record = by_id[sid][-1]
        log = strip_ansi((RUN / "records" / record["log"]).read_text())
        timing = re.search(r"witness_seconds=(\d+) proof_seconds=(\d+) verify_seconds=(\d+)", log)
        elapsed = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([\d:.]+)", log)
        rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", log)
        if timing and elapsed and rss:
            measurements.append(dict(step=sid, label=label, witness_s=int(timing[1]), proof_s=int(timing[2]),
                                     verify_s=int(timing[3]), total_wall=elapsed[1], max_rss_kib=int(rss[1]),
                                     source_record=record["log"]))
    (RUN / "performance.json").write_text(json.dumps(measurements, ensure_ascii=False, indent=2))
    metric_rows = "".join(f"<tr><td>{esc(m['label'])}</td><td>{m['witness_s']}</td><td>{m['proof_s']}</td><td>{m['verify_s']}</td><td>{esc(m['total_wall'])}</td><td>{m['max_rss_kib']/1048576:.2f} GiB</td></tr>" for m in measurements)
    metrics_html = '<h3>端末上の実測結果</h3><table><thead><tr><th>入力</th><th>witness 秒</th><th>proof 秒</th><th>verify 秒</th><th>全体 分:秒</th><th>最大RSS</th></tr></thead><tbody>' + metric_rows + '</tbody></table><p>各入力1回。工程別時間は整数秒、全体時間と最大RSSはGNU time。全体は読み込み等も含む（合成入力は再検証も含む）。0秒は計測分解能による。</p>'
    cards = []
    nav = []
    for step in steps:
        sid = step["id"]
        attempts = by_id.get(sid, [])
        record = attempts[-1] if attempts else None
        status = record["status"] if record else "pending"
        note = notes.get("steps", {}).get(sid, {})
        status_text = {"passed": "完了", "failed": "不一致 / 失敗を記録", "pending": "未実行", "running": "実行中"}[status]
        if note.get("resolved"):
            status_text = "不一致検出 → 後続ステップで対応済み"
        script = record.get("script_text", "") if record else ""
        full_command = script or (shlex.join(record["executed_argv"]) if record else "")
        command = note.get("commands", full_command)
        transcript = strip_ansi((RUN / "records" / record["log"]).read_text()) if record else ""
        excerpt = note.get("evidence", evidence(transcript))
        if note.get("evidence_patterns"):
            excerpt = "\n".join(line for line in transcript.splitlines()
                                if not line.startswith("+") and any(re.search(pattern, line) for pattern in note["evidence_patterns"]))
        location = "エッジPC" if step.get("remote", "script" in step) else "操作元Mac"
        if "command" in step:
            location = "操作元Mac → エッジPC" if step["command"][0] == "scp" else "操作元Mac"
        time_text = f"{record['started_at']} / {record.get('elapsed_seconds', '…')} 秒 / exit {record.get('exit_code', '…')}" if record else "未実行"
        result = note.get("result", "実行ログを参照。" if record else "これから実行します。")
        take = note.get("takeaway", step["expect"])
        history = "".join(f'<li><a href="records/{esc(r["log"])}">試行 {i+1}: {esc(r["status"])} / {esc(r["started_at"])}</a></li>' for i, r in enumerate(attempts))
        cards.append(f'''<section class="step" id="step-{esc(sid)}" data-step="{esc(sid)}">
          <div class="eyebrow">STEP {esc(sid)} · {esc(location)}</div>
          <h2>{esc(step['title'])}</h2><span class="badge {esc(status)}">{esc(status_text)}</span>
          <p class="timing">{esc(time_text)}</p>
          <div class="goal"><b>目的</b><p>{esc(step['purpose'])}</p></div>
          <div class="columns"><div><h3>主要コマンド・再実行例（実行時の全量は詳細）</h3><pre>{esc(command)}</pre></div>
          <div><h3>実際の出力（抜粋）</h3><pre>{esc(excerpt)}</pre></div></div>
          <div class="result"><b>確認結果</b><p>{esc(result)}</p></div>
          <p class="takeaway"><b>発表で説明する点：</b>{esc(take)}</p>
          <details><summary>全コマンド・全ログ・試行履歴</summary><pre>{esc(full_command)}</pre><pre>{esc(transcript)}</pre><ul>{history}</ul></details>
          </section>''')
        nav.append(f'<a href="#step-{esc(sid)}" data-target="{esc(sid)}">{esc(sid)} {esc(step["title"])}</a>')
    installed = notes.get("installed", [])
    rows = "".join(f"<tr><td>{esc(x['name'])}</td><td>{esc(x['version'])}</td><td>{esc(x['role'])}</td></tr>" for x in installed)
    facts = "".join(f"<li>{esc(x)}</li>" for x in notes.get("summary", []))
    limits = "".join(f"<li>{esc(x)}</li>" for x in notes.get("limitations", []))
    sources = [
        ("Node.js v22 公式配布", "https://nodejs.org/en/download/archive/v22"),
        ("uv 公式インストール方法", "https://docs.astral.sh/uv/getting-started/installation/"),
        ("uv管理Pythonの説明", "https://docs.astral.sh/uv/concepts/python-versions/"),
        ("PicoScenes Python Toolbox（固定コミット）", "https://github.com/wifisensing/PicoScenes-Python-Toolbox/tree/f676855accedf79e848bf2f1d10ee5c1f649a33a"),
        ("Playwright ブラウザ導入（資料撮影用）", "https://playwright.dev/docs/browsers"),
    ]
    source_html = "".join(f'<li><a href="{esc(url)}">{esc(label)}</a></li>' for label, url in sources)
    generated = dt.datetime.now().astimezone().isoformat()
    document = '''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PicoScenes Edge / 環境構築記録 2026-10-19</title><style>
:root{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans JP","Hiragino Sans",sans-serif;color:#14293b;background:#eef2f6}
*{box-sizing:border-box}body{margin:0}header{padding:42px 5vw 28px;background:#102a43;color:white}header p{max-width:1000px;line-height:1.8}h1{font-size:30px;margin:8px 0}h2{font-size:25px;margin:10px 0 16px}h3{font-size:15px}p,li{line-height:1.75}a{color:#176d91}.eyebrow{letter-spacing:.13em;color:#387283;font-size:13px;font-weight:700}header .eyebrow{color:#96d6d7}.toolbar{position:sticky;top:0;background:#fff;z-index:5;border-bottom:1px solid #ced8e1;padding:12px 3vw;display:flex;align-items:center;gap:10px;flex-wrap:wrap}button,select{font:inherit;padding:8px 14px;border:1px solid #b9cad6;border-radius:6px;background:#fff;color:#173e57;cursor:pointer}main{max-width:1450px;margin:auto;padding:24px}.overview,.step{background:white;border:1px solid #dbe3e8;border-radius:12px;padding:30px;margin-bottom:24px;box-shadow:0 5px 20px #14293b05}.step{scroll-margin-top:85px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:22px}.columns>div{min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f8;padding:16px;border-radius:6px;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;tab-size:2;margin:10px 0}.badge{font-size:13px;font-weight:700;display:inline-block;border-radius:20px;background:#e9edf1;padding:5px 12px}.passed{background:#dff3e9;color:#175d43}.failed{background:#fff0d9;color:#825010}.timing{font-size:12px;color:#627d91}.goal p,.result p{margin:4px 0}.result{background:#eaf5f5;border-left:4px solid #2e8b83;padding:14px 18px;margin-top:16px}.takeaway{font-size:14px}details{border-top:1px solid #dde6ed;margin-top:18px;padding-top:12px;color:#4b6071}summary{cursor:pointer}details pre{font-size:12px}nav{display:flex;gap:6px 20px;flex-wrap:wrap}nav a{font-size:13px;text-decoration:none;padding:3px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #dde6ed;padding:9px 12px;text-align:left}footer{padding:25px;color:#627d91;font-size:12px}.capture header,.capture .overview,.capture footer{display:none}.capture main{max-width:1450px;padding:20px}.capture .step{display:none}.capture .step.active{display:block}.capture .toolbar{position:static}.capture details{display:none}.capture .step h2{font-size:27px}.capture .columns pre{font-size:14px}.capture .step{box-shadow:none}.help{font-size:13px;color:#4b6071}.notice{padding:12px 16px;background:#fff7e5;border-left:4px solid #d2a44e}
@media(max-width:850px){.columns{grid-template-columns:1fr}main{padding:12px}.step,.overview{padding:20px}}
@media print{body{background:#fff}.toolbar,nav,details{display:none!important}.step{break-before:page;box-shadow:none;border:0}.capture .step.active{display:block}header{background:white;color:#102a43}.overview{box-shadow:none}}
</style></head><body>
<header><div class="eyebrow">RESEARCH EXECUTION RECORD · 2026 / 10 / 19</div><h1>PicoScenesエッジPC 証明生成環境の構築記録</h1><p>対象：infonetworking@100.111.253.60 · Ubuntu 22.04.5 · Core i5-12450H / 8コア12スレッド / 約16GB RAM<br>インストールを独立ステップとして記録。各カードに目的・実行コマンド・実出力・結果・発表ポイントを掲載。</p></header>
<div class="toolbar"><button id="mode">スクショモードに切り替え</button><button id="prev">← 前</button><select id="selector"></select><button id="next">次 →</button><button onclick="window.print()">印刷 / PDF保存</button><span class="help">スクショモードで1ステップ表示。ブラウザの拡大率を調整して撮影。</span></div>
<main><section class="overview"><h2>到達点と資料の読み方</h2><ul>__FACTS__</ul><p>操作場所はカードに明示。所要時間はSSH・ダウンロード等を含むステップ全体の時間で、証明時間とは別。失敗した試行も削除せず保持しています。</p><p class="notice">今回の対象は既存の64観測×8サブキャリア回路を動かす環境の構築です。「全サブキャリア比較」「判定値だけの公開」「オンチェーン検証」の完成を意味しません。</p><h3>導入・確認したツール</h3><table><thead><tr><th>ツール</th><th>バージョン</th><th>用途</th></tr></thead><tbody>__TOOLS__</tbody></table><h3>ステップ一覧</h3><nav>__NAV__</nav><h3>操作手順</h3><pre>ssh infonetworking@100.111.253.60
source /home/infonetworking/csi-zkp/env.sh
cd /home/infonetworking/csi-zkp/packages/lomb_scargle_e2e
./bin/self_test.sh

# 結果ファイル名は毎回変えて保存
./bin/prove.sh /home/infonetworking/csi_data/main/csi_20261005_115619.csi /home/infonetworking/csi-zkp/results/my_run_01.json
./bin/verify.sh /home/infonetworking/csi-zkp/results/my_run_01.json</pre><h3>制約・今後の課題</h3><ul>__LIMITS__</ul><h3>参照した一次資料</h3><ul>__SOURCES__</ul></section>__CARDS__</main><footer>生成時刻：__GENERATED__ · records/ に実行ログとJSONメタデータ。findings.json に説明文。生CSI・秘密入力・witnessはこの資料に含めません。</footer>
<script>
const cards=[...document.querySelectorAll('.step')],select=document.querySelector('#selector');let index=0;
cards.forEach((c,i)=>{const o=document.createElement('option');o.value=i;o.textContent=c.dataset.step+' '+c.querySelector('h2').textContent;select.append(o)});
function show(i){index=Math.max(0,Math.min(cards.length-1,i));cards.forEach((c,n)=>c.classList.toggle('active',n===index));select.value=index;history.replaceState(null,'','#step-'+cards[index].dataset.step);if(!document.body.classList.contains('capture'))cards[index].scrollIntoView();else window.scrollTo(0,0)}
document.querySelector('#mode').onclick=()=>{document.body.classList.toggle('capture');document.querySelector('#mode').textContent=document.body.classList.contains('capture')?'一覧に戻る':'スクショモードに切り替え';show(index)};
document.querySelector('#prev').onclick=()=>show(index-1);document.querySelector('#next').onclick=()=>show(index+1);select.onchange=()=>show(Number(select.value));
document.querySelectorAll('nav a').forEach(a=>a.onclick=()=>{index=cards.findIndex(c=>c.dataset.step===a.dataset.target);select.value=index});
document.addEventListener('keydown',e=>{if(e.target.tagName==='SELECT')return;if(e.key==='ArrowRight')show(index+1);if(e.key==='ArrowLeft')show(index-1)});
const requested=location.hash.replace('#step-',''),found=cards.findIndex(c=>c.dataset.step===requested);if(found>=0)index=found;cards[index]?.classList.add('active');select.value=index;
if(new URLSearchParams(location.search).has('capture')){document.body.classList.add('capture');document.querySelector('#mode').textContent='一覧に戻る'}
</script></body></html>'''
    replacements = {"__FACTS__": facts, "__TOOLS__": rows, "__NAV__": "".join(nav), "__CARDS__": "".join(cards),
                    "__LIMITS__": limits, "__SOURCES__": source_html, "__GENERATED__": esc(generated)}
    for marker, value in replacements.items():
        document = document.replace(marker, value)
    document = document.replace('<h3>ステップ一覧</h3>', metrics_html + '<h3>ステップ一覧</h3>')
    (RUN / "report.html").write_text(document)
    print(RUN / "report.html")


if __name__ == "__main__":
    main()
