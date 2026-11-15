// Offline report + screenshots using the already installed local browser tools.
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const renderer=path.resolve(__dirname,'../edge-setup/artifacts/report-renderer');
const {chromium}=require(path.join(renderer,'node_modules/playwright'));
const out=path.resolve(process.argv[2]);
const names=['synthetic-15','synthetic-30','synthetic-48','real-A','real-B','real-C'];
const results=Object.fromEntries(names.map(n=>[n,JSON.parse(fs.readFileSync(path.join(out,n,'summary.json'),'utf8'))]));
const actions=JSON.parse(fs.readFileSync(path.join(out,'execution.json'),'utf8'));
const locations=JSON.parse(fs.readFileSync(path.join(out,'locations.json'),'utf8'));
assert(actions.every(a=>a.status==='passed'));
names.forEach(n=>{const p=results[n].vmd_proof;assert(p.verified&&p.matches_integer_reference&&p.tampered_verdict_rejected);assert.equal(p.public_signal_count,5);});
names.slice(3).forEach(n=>{assert.equal(results[n].metadata.original_series,980);assert.equal(results[n].metadata.selected_series,256);});
const initial=path.resolve(out,'../vmd-20261019T123127');
fs.mkdirSync(path.join(out,'initial-run'),{recursive:true});
for(const item of fs.readdirSync(initial,{withFileTypes:true})){
  if(item.name.startsWith('report')||item.name==='screenshots')continue;
  fs.cpSync(path.join(initial,item.name),path.join(out,'initial-run',item.name),{recursive:true});
}
const initialActions=JSON.parse(fs.readFileSync(path.join(initial,'execution.json'),'utf8'));
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=3)=>v==null?'—':Number(v).toFixed(d);
const table=(heads,rows)=>`<table><thead><tr>${heads.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
const card=(id,title,body)=>`<section class="card" id="${id}"><div class="eyebrow">VMD / LOMB–SCARGLE · ${esc(locations.run_id)} · ${id}</div><h2>${esc(title)}</h2>${body}</section>`;
const bpm=(n,key)=>num(results[n][key].result.bpm);
let cards='';
cards+=card('revision','初回測定の確認と、比較条件の修正',`<p>初回実行 vmd-20261019T123127 の結果は削除せずinitial-run/に保存しています。以下を修正し、別パッケージ・別出力先ですべて再測定しました。</p><ol><li>最初に流用したエッジ用読込器は8系列へ間引いていました。修正版は全980系列を保持する既存のバッチ読込器を使用し、PythonでSNRを評価して256系列を選びます。これは245サブキャリア×送受信2×2の系列数であり、980物理サブキャリアではありません。</li><li>128点・2 HzのLS探索上限を1 Hz未満へ変更しました。初回の1.5 Hz上限は等間隔2 Hz入力のNyquist周波数を超え、折り返しピークを選ぶ恐れがありました。</li></ol><p class="note">以下の比較表は修正版の結果です。初回ログも保存し、初回の8系列解析を全系列解析として報告しません。全系列のSNR評価はPython側のみで、VMD証明の範囲には含まれません。</p>`);
cards+=card('overview','エッジで通常VMDと近似VMD証明を動かす',`<p>通常の浮動小数点VMDと、既存の固定小数点近似VMD回路を配置。合成3入力・実CSI3件で、解析と証明生成・検証を実行しました。</p>${table(['構成','入力と範囲','実行状態'],[
['通常VMD','共通PCA波形、vmdpy 0.2、5モード、alpha=2000、tau=0、DC=0、init=1、tol=1e-7','端末内Python解析'],
['比較用Lomb–Scargle','通常VMDと同じPCA波形・時刻、0.05..1.5 Hzの1000周波数点','端末内Python解析（証明ではない）'],
['近似VMD','128点・2 Hz・3モード・4反復、整数範囲[-100,100]','Groth16生成・検証・判定改変拒否'],
['既存Lomb–Scargle証明','従来の64×8 CSI入力。今回のPCA波形とは別','既存self-testも再実行して成功']])}<p class="note">「通常VMD」と「近似VMD」は同じ計算ではありません。近似VMDの証明は生CSIからの前処理全体を保証しません。</p>`);
cards+=card('protocol','比較条件と、既存方式から変えた点',`<ol><li>実CSIを端末内で読込み、時刻で整列・重複除去。</li><li>CSI振幅を実時刻に沿って100 Hz等間隔へ線形補間。外挿せず、偶数点に揃える。</li><li>全入力系列のSNRをPythonで評価し最大256系列を選択。0.1..1 Hzの既存Butterworthフィルタ、PCA 3成分、共通のFFT帯域比による1成分選択。</li><li>同じPCA波形を浮動小数点LSと通常VMDへ渡す。</li><li>同じ波形を2 Hz・128点に縮約・量子化。これをLS、通常VMD、整数近似VMDへ共通入力し、近似VMDの証明も作る。</li></ol><p>Python解析は方式・入力ごとにウォームアップ1回＋測定3回。前処理は共通で1回のみ。BLAS/OpenMPは1スレッドに固定。証明生成は各入力1回。</p><p class="note">以前のバックエンドの固定100 Hz仮定をそのまま実パケット列へ適用していません。今回の時刻補間・full SVD・共通PC選択は比較用アダプタの条件であり、過去の解析結果との直接比較には注意が必要です。補間で元データの情報量が増えるわけではありません。</p>`);
cards+=card('real-results','実CSI：同じ波形での推定BPM比較',table(['入力','通常LS（長い共通波形）','通常VMD（長い共通波形）','LS（128点）','通常VMD（128点）','近似VMD（128点）'],['real-A','real-B','real-C'].map(n=>[n,bpm(n,'float_ls'),bpm(n,'float_vmd'),bpm(n,'compact_float_ls'),bpm(n,'compact_float_vmd'),bpm(n,'compact_integer_vmd')]))+
`<p>A＝10/05 11:56、B＝10/05 11:55、C＝09/07 18:51収録。128点LSの探索域は0.05 Hz以上1 Hz未満、1000点。</p>${table(['入力','元の平均packet/s','最大時刻間隔 秒','等間隔化後の点数','128点化でのゼロ追加数'],['real-A','real-B','real-C'].map(n=>{const m=results[n].metadata;return[n,num(m.mean_packet_rate_hz),num(m.max_gap_seconds),m.uniform_samples,m.approximation_padded_samples];}))}<p class="note">実CSIの正解BPMは未提供。特にBは約6.7秒の空白を補間しており、結果の解釈に注意が必要です。数値の違いから高精度な方式は決められません。128点化では時間長・帯域・量子化・ゼロ詰めも変わるため、長い波形との差を近似式だけの誤差と呼ぶこともできません。</p>`);
cards+=card('synthetic-results','合成信号：既知の15・30・48 BPMで確認',table(['真値BPM','通常LS','通常VMD','128点LS','128点通常VMD','128点近似VMD'],names.slice(0,3).map(n=>[results[n].metadata.true_bpm,bpm(n,'float_ls'),bpm(n,'float_vmd'),bpm(n,'compact_float_ls'),bpm(n,'compact_float_vmd'),bpm(n,'compact_integer_vmd')]))+
`<p>単一の正弦波。100 Hz・6400点（64秒）を生成し、短い入力は同じ波形から変換。合成信号にはCSIの前処理を適用していません。</p><p>通常VMDは既存の「6〜22 BPM内のピークを持つモードを優先し、ピーク比で選ぶ」規則。LSの主表示は全探索域の最大ピークで、帯域内ピークはJSONにも別記しています。これは同一の判定規則ではありません。</p><p class="note">特に帯域外の合成信号では、微小な帯域内モードを優先する選択規則の影響も確認対象です。正常／異常の医学的な閾値や臨床精度を検証した実験ではありません。</p>`);
cards+=card('timing','解析時間と証明時間を分けて記録',table(['入力','通常LS 秒','通常VMD 秒','128点通常VMD 秒','整数近似VMD Python秒','近似VMD証明 秒'],names.map(n=>[n,num(results[n].float_ls.median_seconds),num(results[n].float_vmd.median_seconds),num(results[n].compact_float_vmd.median_seconds),num(results[n].compact_integer_vmd.median_seconds),num(results[n].vmd_proof.proof_seconds)]))+
`<p>解析は同一プロセス内3回の中央値。読込み・共通前処理・プロセス起動を含みません。整数参照の時間には三角関数テーブルの再作成を含み、回路の実行時間ではありません。</p><p>証明欄はGroth16 proveの1回の時間で、witness生成・検証は含みません。詳細は各summary.json。GNU timeの各*.time.txtは、その入力の全解析反復と証明を合わせたプロセスの時間・最大RSSであり、個々のアルゴリズム別RSSではありません。</p><p class="note">既存LS証明は64×8 CSIからの処理、近似VMD証明は前処理後の128点からの処理です。証明範囲と計算量が異なるので、証明時間だけでVMDが有利とは結論できません。</p>`);
cards+=card('proof-scope','証明で確認した範囲・次に残る課題',`<ul><li>6入力すべてで証明検証成功。判定・周波数bin・選択モードが整数Python参照と一致。</li><li>同じ証明の公開判定値だけを反転した場合、6入力すべてInvalid proof。</li><li>公開信号は5個。判定・周波数bin・選択モード・中間ハッシュ・親コミットメント。</li><li>今回はparentCommitment=0。前段証明とは未接続で、生CSI→補間→SNR選択→フィルタ→PCAの正しさは証明対象外。</li><li>nonce・入力波形・witnessは端末内の一時ディレクトリで処理し、処理終了時に削除。元CSIと以前の証明は保持。</li><li>既存WASM・鍵を再利用し、再コンパイルや新たなTrusted Setupはしていない。動作確認は回路全体の健全性監査ではない。</li></ul><p class="note">次の精度比較には、正解呼吸数のある実CSI、前処理とピーク選択規則の統一、近似パラメータを1つずつ変えた実験が必要です。判定1ビットだけの公開・前段証明との接続も未実装です。</p>`);
cards+=card('usage','エッジでの再実行方法',`<pre>ssh infonetworking@100.111.253.60
source /home/infonetworking/csi-zkp/env.sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
python3 ${esc(locations.package)}/worker.py --source /home/infonetworking/csi_data/main/csi_20261005_115619.csi --output /home/infonetworking/csi-zkp/results/vmd-my-new-run</pre><p>出力先は必ず新しい名前にしてください。既存ディレクトリへの上書きは拒否します。入力は30〜120秒の収録を対象にしています。</p><p>証明本体と公開信号はエッジ側の各ケースのproof/に保存。この報告用ZIPには生CSI・入力波形・witness・証明本体を含めません。</p><p>導入したライブラリは joblib 1.4.2、threadpoolctl 3.5.0、scikit-learn 1.5.2、vmdpy 0.2。既存NumPy 1.26.4・SciPy 1.15.3は維持しました。</p><p>一次資料：<a href="https://pypi.org/project/vmdpy/0.2/">vmdpy 0.2</a>、<a href="https://github.com/vrcarva/vmdpy/blob/master/vmdpy/vmdpy.py">VMD実装</a>、<a href="https://pypi.org/project/scikit-learn/1.5.2/">scikit-learn依存仕様</a>、<a href="https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.signal.lombscargle.html">SciPy Lomb–Scargle</a>。</p>`);
const reportActions=[...initialActions.slice(0,6).map(a=>({...a,initial:true,log:'initial-run/'+a.log})),...actions];
for(const a of reportActions){
  const raw=fs.readFileSync(path.join(out,a.log),'utf8').replace(/\x1b\[[0-?]*[ -/]*[@-~]/g,'').split('\n').slice(1).join('\n');
  const useful=raw.split('\n').filter(l=>/Successfully installed|Requirement already satisfied|^Name:|^Version:|No broken|^manifest|^Ran |^OK$|^test_|: OK|self-test passed|"verified"|"matches_integer_reference"|"tampered_verdict_rejected"|"public_signal_count"|"chain_linked"|"proof_seconds"|"sha256"|^1\.26|^Mem:|PicoScenes|archive/.test(l));
  let excerpt=useful.slice(-15).join('\n')||raw.trim().split('\n').slice(-10).join('\n')||'標準出力なし。終了コード0を記録。';
  const command=a.argv[0]==='ssh'?a.argv[a.argv.length-1]:a.argv.join(' ');
  cards+=card(`${a.initial?'initial-':''}step-${String(a.step).padStart(2,'0')}`,`${a.initial?'初回導入 ':''}STEP ${a.step}：${a.title}`,`<p class="badge">完了 · exit ${a.exit_code} · ${num(a.seconds)}秒</p><p>${esc(a.started_at)}</p><h3>実際の出力（抜粋）</h3><pre>${esc(excerpt)}</pre><p><a href="${esc(a.log)}">コマンドと出力の全量</a>を保存。所要時間には転送やインストールも含みます。</p><details><summary>実行コマンドの全量</summary><pre>${esc(command)}</pre></details>`);
}
const csv=[['case','method','bpm','median_analysis_seconds','proof_seconds','ground_truth_bpm']];
for(const n of names){for(const key of ['float_ls','float_vmd','compact_float_ls','compact_float_vmd','compact_integer_vmd','vmd_proof']){
  const r=results[n][key];csv.push([n,key,r.result.bpm,r.median_seconds??'',r.proof_seconds??'',results[n].metadata.true_bpm??'']);}}
fs.writeFileSync(path.join(out,'comparison.csv'),csv.map(row=>row.map(x=>JSON.stringify(x)).join(',')).join('\n')+'\n');
fs.writeFileSync(path.join(out,'report.html'),`<!doctype html><html lang="ja"><meta charset="utf-8"><title>エッジVMD導入・LS比較</title><style>
*{box-sizing:border-box}body{margin:0;color:#14334a;background:#eef3f7;font:16px/1.8 -apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN",sans-serif}main{max-width:1440px;margin:auto;padding:24px}.card{background:white;border:1px solid #d4e0e8;border-radius:12px;padding:32px;margin-bottom:24px}h2{font-size:26px;margin:12px 0 22px}h3{font-size:17px}.eyebrow{font-size:12px;letter-spacing:.08em;color:#347180;font-weight:bold}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #d5e1e8;padding:10px 9px;text-align:left}th{background:#eff5f8}pre{font:13px/1.65 monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#eff4f8;padding:18px;border-radius:6px}.note{background:#edf7f5;border-left:4px solid #35877d;padding:12px 18px}.badge{background:#e0f3e9;padding:5px 12px;display:inline-block;border-radius:15px}a{color:#166a89}details{margin-top:20px}body.capture details{display:none}@media print{.card{break-before:page;border:0}details{display:none}main{padding:0}}
</style><main>${cards}</main></html>`);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:path.join(renderer,'browsers/manual-chromium-1194/chrome-mac/headless_shell')});
  try{
    const page=await browser.newPage({viewport:{width:1500,height:1100},deviceScaleFactor:1.5});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(pathToFileURL(path.join(out,'report.html')).href);await page.evaluate(()=>document.fonts.ready);
    await page.locator('body').evaluate(e=>e.classList.add('capture'));
    fs.mkdirSync(path.join(out,'screenshots'),{recursive:true});
    for(const el of await page.locator('.card').all()){
      const id=await el.getAttribute('id');assert.equal(await el.evaluate(e=>e.scrollWidth>e.clientWidth+2),false);
      await el.screenshot({path:path.join(out,'screenshots',id+'.png')});console.log('Captured '+id);
    }
    await page.pdf({path:path.join(out,'report.pdf'),format:'A4',landscape:true,scale:.68,printBackground:true,
      margin:{top:'10mm',bottom:'10mm',left:'10mm',right:'10mm'}});
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(out,'report-validation.json'),JSON.stringify({passed:true,cases:names.length,steps:actions.length,
      screenshots:await page.locator('.card').count(),browser:browser.version()},null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
