const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const number = (value) =>
  value == null
    ? "未計測"
    : Number(value).toLocaleString("ja-JP", { maximumFractionDigits: 1 });
export function renderReport(r) {
  const labels = {
    fabric: "Hyperledger Fabric",
    sepolia: "Ethereum Sepolia",
    "local-evm": "ローカル EVM",
  };
  const max = Math.max(
    1,
    ...r.summaries.map((s) => s.metrics.recordCommitMs.median || 0),
  );
  return `<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CSI 証明基盤の比較</title>
 <style>*{box-sizing:border-box}body{margin:0;background:#f4f7f5;color:#193e34;font:15px/1.8 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:44px 24px}header{display:flex;justify-content:space-between;border-bottom:1px solid #ceddd4;padding-bottom:18px}.tag{font-size:12px;border:1px solid #ccdcd2;border-radius:20px;padding:3px 12px}h1{font-size:36px;line-height:1.4;letter-spacing:-1px;margin:35px 0 14px}h2{font-size:18px;margin:0 0 18px}.muted{color:#5c7167}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:28px 0}.card,section{background:white;border:1px solid #d8e4dd;border-radius:16px;padding:24px}strong.big{display:block;font-size:32px;line-height:1.6}.bar{background:#e9f0eb;height:10px;border-radius:5px;margin-top:18px}.bar span{display:block;background:#33765c;height:10px;border-radius:5px}section{margin:20px 0}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{text-align:left;padding:12px;border-bottom:1px solid #e5ece7;font-size:13px}th{color:#536c5e}small{font-size:12px}.note{background:#fff9e9;border:1px solid #e8ddb8;border-radius:12px;padding:16px;color:#6a5724}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}summary{cursor:pointer}footer{overflow-wrap:anywhere;font-size:12px;color:#60756a}@media(max-width:600px){h1{font-size:28px}main{padding:24px 16px}}</style>
 <main><header><b>CSI Care <span class="muted">/ Research</span></b><span class="tag">LEDGER BENCHMARK</span></header>
 <h1>証明の記録と検証を、<br>同じ条件で比較する。</h1><p class="muted">同一のGroth16証明 · 交互の実行順序 · ウォームアップ ${r.warmup} 回 / 本計測 ${r.trials} 回</p>
 ${!r.targets.includes("sepolia") ? '<div class="note">Sepoliaは未計測です。下記のEVM値はローカル環境の実測であり、Sepoliaの性能や料金を表すものではありません。</div>' : ""}
 <div class="grid">${r.summaries.map((s) => `<div class="card"><h2>${labels[s.target]}</h2><small class="muted">記録の確定待ちを含む中央値</small><strong class="big">${number(s.metrics.recordCommitMs.median)} <small>ms</small></strong><small>成功 ${s.succeeded} / ${s.attempted}　失敗 ${s.failed}</small><div class="bar"><span style="width:${((s.metrics.recordCommitMs.median || 0) / max) * 100}%"></span></div></div>`).join("")}</div>
 <section><h2>処理時間</h2><p class="muted">単位 ms / 中央値（p95）。証明生成時間は同じ試料の計測値を両列で共有します。</p><div class="scroll"><table><thead><tr><th>工程</th>${r.summaries.map((s) => `<th>${labels[s.target]}</th>`).join("")}</tr></thead><tbody>${Object.entries(
   {
     proofGenerationMs: "証明生成処理",
     recordCommitMs: "記録 → 確定条件",
     verifyReadMs: "記録後の検証・結果取得",
     totalMs: "上記3工程の合計",
   },
 )
   .map(
     ([k, label]) =>
       `<tr><td>${label}</td>${r.summaries.map((s) => `<td>${number(s.metrics[k].median)} (${number(s.metrics[k].p95)})</td>`).join("")}</tr>`,
   )
   .join("")}</tbody></table></div></section>
 <section><h2>コストと比較条件</h2><div class="scroll"><table><tr><th>基盤</th><th>記録gas（中央値）</th><th>全本計測の記録手数料合計</th></tr>${r.summaries.map((s) => `<tr><td>${labels[s.target]}</td><td>${s.target === "fabric" ? "gasなし" : number(s.gasUsed.median)}</td><td>${s.target === "fabric" ? "ネイティブ通貨の取引手数料なし" : escape(s.feesWei.reduce((a, b) => a + BigInt(b), 0n)) + " wei（テスト通貨）" + (s.unknownFeeCount ? " / 未確定 " + s.unknownFeeCount + " 件は合計対象外" : "")}</td></tr>`).join("")}</table></div><p class="muted">Fabricのサーバー・証明書管理・運用費は別途必要です。両基盤とも照会は読み取り実行で、検証トランザクションの送信手数料は発生しません。</p><p>${r.infrastructureAssumptions ? `運用費の配賦試算：${escape(JSON.stringify(r.infrastructureAssumptions))}` : "運用費：単価・想定処理量が未指定のため未算出。総コストが無料という意味ではありません。"}</p></section>
 <section><h2>測定の範囲</h2><p>入力：${escape(r.inputKind)}。${r.debugMode ? "デバッグ条件での動作確認です。" : "通常入力条件です。"} CSI取得時間・APIキュー待ち・初期接続時間は含みません。</p><p>証明生成の範囲：${escape(r.proofGenerationScope || "snarkjs fullProve (witness + prove)")}<br>CSI前処理：${number(r.preprocessingMs)} ms（参考値、合計には含めません）</p><p>Fabricは2組織・各1 peer・1 ordererの同一ホスト上のテスト構成です。実運用の複数拠点構成との性能差は別途測定が必要です。</p><details><summary>構成・確認条件を表示</summary><pre>${escape(JSON.stringify(r.metadata, null, 2))}</pre></details><details><summary>全試行のデータを表示</summary><pre>${escape(JSON.stringify(r.rows, null, 2))}</pre></details></section>
 <footer>実行ID ${escape(r.runId)}<br>${escape(r.startedAt)}<br>検証鍵 ${escape(r.verificationKeyHash)}</footer></main></html>`;
}
