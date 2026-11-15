// Render measured evidence using the screenshot tools installed in the setup task.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const rendererRoot = path.resolve(__dirname, '../edge-setup/artifacts/report-renderer');
const {chromium} = require(path.join(rendererRoot, 'node_modules/playwright'));
const out = path.resolve(process.argv[2]);
const summary = JSON.parse(fs.readFileSync(path.join(out, 'summary.json'), 'utf8'));
const actions = JSON.parse(fs.readFileSync(path.join(out, 'execution.json'), 'utf8'));
assert.equal(summary.status, 'passed');
assert.equal(summary.completed_trials, 18);
assert.equal(summary.sources_unchanged, true);
assert.equal(summary.results.length, 3);
summary.results.forEach(r => { assert.equal(r.runs, 5); assert(r.all_verified && r.all_match_baseline); });
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => Number(n).toFixed(3);
const table = (head, rows) => `<table><thead><tr>${head.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
const card = (id, title, content) => `<section class="card" id="${id}"><div class="eyebrow">EDGE EXPERIMENT · ${esc(summary.protocol.run_id)} · ${id}</div><h2>${title}</h2>${content}</section>`;
const metricRows = key => summary.results.map(r => [r.case, r.source, r.runs, num(r[key].median),
  `${num(r[key].min)} – ${num(r[key].max)}`, num(r[key].sample_sd)]);
const head = ['入力', 'ファイル', '回数', '中央値', '最小 – 最大', '標本標準偏差'];
let cards = '';
cards += card('01-protocol', '実験条件：現行回路の基準測定', `<p>目的は、同じCSIに対する判定の再現性と処理時間・メモリのばらつきを調べること。判定1ビット版やVMDとの比較ではありません。</p>
<ul><li>実CSI 3件。各1回ウォームアップ後、各5回を測定（合計18回）。</li><li>逐次実行。測定順はABC → BCA → CAB → ABC → BCA。</li><li>既存のprove.sh・回路・証明鍵は変更なし。新規ツールの導入なし。</li><li>OSキャッシュを消さず測定。PicoScenesの既存プロセスは停止しない。</li><li>64観測×8系列・32周波数bin・公開信号69個の既存構成。</li></ul>
<pre>source /home/infonetworking/csi-zkp/env.sh\npython3 /home/infonetworking/csi-zkp/scripts/${esc(summary.protocol.run_id)}.py --run-id NEW_EXPERIMENT_ID --repetitions 5</pre><p class="note">正解呼吸数を使った精度評価、別方式との優劣比較ではありません。再実行時はNEW_EXPERIMENT_IDを未使用の英数字・ハイフン・アンダースコアからなるIDに置き換えてください。</p>`);
cards += card('02-environment', '実験前後の環境とデータ保全', `<p>UbuntuエッジPC · Core i5-12450H · 約16 GB RAM<br>実行時バージョン：Node ${esc(summary.before.node)} / ${esc(summary.before.python)}</p>
<div class="columns"><div><h3>実験前</h3><pre>${esc(summary.before.time)}\nloadavg: ${esc(summary.before.loadavg)}\n${esc(summary.before.picoscenes)}</pre></div><div><h3>実験後</h3><pre>${esc(summary.after.time)}\nloadavg: ${esc(summary.after.loadavg)}\n${esc(summary.after.picoscenes)}</pre></div></div>
<p>元CSI 3件のSHA-256は実験前後で一致。実験前後のパッケージmanifest検査に成功。新しい証明は専用実験フォルダへ保存し、以前の証明も保持しました。</p><p>生CSI・秘密入力・witness・今回の証明本体は操作元へ回収していません。回収対象は測定ログと集計データのみです。</p>`);
cards += card('03-time', '全体処理時間の比較［秒］', table(head, metricRows('total_seconds')) +
 `<p>各5回。CSI読込・入力変換・witness生成・証明生成・検証・結果保存を含む既存prove.sh全体を測定しました。外側のプロセス起動・待機・GNU time起動の小さなオーバーヘッドも含みます。</p><p>単調増加時計で測定。保存後に別途行う再検証は、この全体処理時間に含めません。表示は小数3桁ですが、精度を保証するものではありません。</p><p class="note">ファイルのフレーム数は異なっても、証明回路への入力はすべて64×8です。全入力規模への処理時間の比例関係を測った実験ではありません。</p>`);
cards += card('04-memory', '最大RSSの比較［GiB］', table(head, metricRows('max_rss_gib')) +
 `<p>各実行のGNU time最大RSSを集計。1 GiB = 1,048,576 KiB。</p><p>この値はコマンドと子プロセスについてGNU timeが報告する最大RSSであり、並行する全プロセスの使用量の合計や、端末全体のピークメモリではありません。測定値だけで同時実行数や必要搭載メモリを決めることはできません。</p><p class="note">今回の実験は1件ずつ実行。PicoScenesの収集品質・欠落率への影響は測定していません。</p>`);
cards += card('05-reproducibility', '証明の再検証と判定の再現性', table(['入力', '判定 isNormal', '測定5回の検証', '既存結果との一致'], summary.results.map(r=>[r.case, String(r.isNormal), '5 / 5 成功', '5 / 5 一致'])) +
 `<p>ウォームアップを含む18件すべてで、証明生成時の検証と、保存JSONからの独立した再検証に成功しました。</p><p>各入力について、環境構築時の証明も改めて検証しました。今回の公開信号69個のうち、乱数で変わるコミットメントを除いた68個を既存結果と比較し、一致を確認しました。証明のバイト列そのものは比較していません。</p><h3>保存証明の独立した再検証時間［秒］</h3>${table(['入力', '中央値', '最小 – 最大'], summary.results.map(r=>[r.case,num(r.reverify_seconds.median),`${num(r.reverify_seconds.min)} – ${num(r.reverify_seconds.max)}`]))}<p>再検証時間にはPython/Node起動、一時ファイルの処理も含みます。falseという値を臨床的な異常の正解とみなすことはできません。</p>`);
cards += card('06-next', '今回言えること・言えないこと', `<h3>確認できたこと</h3><ul><li>現行回路を搭載PC上で反復実行し、3入力について各5回の性能分布を得た。</li><li>同じ入力では判定とコミットメント以外の公開信号が再現した。</li><li>元CSIを変更せず、保存証明を再検証できた。</li></ul><h3>まだ確認していないこと</h3><ul><li>判定1ビット版との性能差・情報非公開化。</li><li>Lomb–Scargle / VMDの精度差、近似計算と浮動小数点計算の誤差。</li><li>全サブキャリア比較・段階的証明・オンチェーン検証。</li><li>長時間連続運転、同時実行、CPU温度・電力・収集欠落率。</li></ul><p class="note">次の比較では、変更点を1つに絞り、同じ入力・測定条件でこの基準と比べます。5回の測定から一般的な速度優位や臨床的精度は結論できません。</p>`);
const actionLinks = actions.map(a=>`<li>${esc(a.step)}. ${esc(a.title)}：exit ${esc(a.exit_code)} / ${num(a.elapsed_seconds)} 秒 <a href="${esc(a.log)}">実行ログ</a></li>`).join('');
const html = `<!doctype html><html lang="ja"><meta charset="utf-8"><title>エッジPC 基準比較実験</title><style>
*{box-sizing:border-box}body{margin:0;background:#eef3f7;color:#14334a;font:16px/1.8 -apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN",sans-serif}main{max-width:1440px;margin:auto;padding:24px}header{padding:25px 40px;background:#14334a;color:white}h1{font-size:28px}h2{font-size:27px;margin:12px 0 22px}h3{font-size:18px}.card{background:white;border:1px solid #d4e0e8;border-radius:12px;padding:34px;margin:0 0 24px}.eyebrow{font-size:13px;color:#387080;font-weight:bold;letter-spacing:.08em}table{border-collapse:collapse;width:100%;font-size:15px}th,td{border-bottom:1px solid #d5e1e8;padding:12px 10px;text-align:left}th{background:#eff5f8}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 monospace;padding:18px;background:#eff4f8;border-radius:8px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}.columns>div{min-width:0}.note{background:#edf7f5;border-left:4px solid #35877d;padding:15px 20px}a{color:#166a89}@media print{header{background:white;color:#14334a}.card{break-before:page;box-shadow:none;border:0}main{padding:0}.records{break-before:page}}
</style><header><h1>エッジPC 現行回路の基準比較実験</h1><p>実測データから生成 · ${esc(summary.protocol.run_id)} · 新規ツール導入なし</p></header><main>${cards}<section class="records"><h2>各操作の記録</h2><ul>${actionLinks}</ul><p><a href="trials.csv">全18試行 CSV</a> · <a href="summary.json">集計と環境情報 JSON</a> · <a href="protocol.json">実験条件 JSON</a></p><p>各試行の実行ログはlogs/、GNU time出力はtimings/。端末の証明本体は /home/infonetworking/csi-zkp/results/benchmarks/${esc(summary.protocol.run_id)}/proofs/ に保存。</p></section></main></html>`;
fs.writeFileSync(path.join(out, 'report.html'), html);
(async()=>{
  const browser = await chromium.launch({headless:true, executablePath:path.join(rendererRoot, 'browsers/manual-chromium-1194/chrome-mac/headless_shell')});
  try {
    const page=await browser.newPage({viewport:{width:1500,height:1100},deviceScaleFactor:1.5});
    const errors=[];
    page.on('pageerror', error=>errors.push(String(error)));
    await page.goto(pathToFileURL(path.join(out,'report.html')).href);
    await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.locator('.card').count(),6);
    fs.mkdirSync(path.join(out,'screenshots'),{recursive:true});
    for(const el of await page.locator('.card').all()) {
      const id=await el.getAttribute('id');
      assert.equal(await el.evaluate(e=>e.scrollWidth>e.clientWidth+2),false);
      await el.screenshot({path:path.join(out,'screenshots',`${id}.png`)});
      console.log('Captured '+id);
    }
    await page.pdf({path:path.join(out,'report.pdf'),format:'A4',landscape:true,scale:0.68,printBackground:true,
      margin:{top:'10mm',bottom:'10mm',left:'10mm',right:'10mm'}});
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(out,'report-validation.json'),JSON.stringify({passed:true,cards:6,browser:browser.version(),
      checks:['18 trials','5 measured trials per case','all verified and reproducible','sources unchanged','6 screenshots','no card overflow','no JavaScript errors']},null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
