#!/usr/bin/env python3
"""Build a local, screenshot-friendly report from measured JSON/CSV artifacts."""
from __future__ import annotations
import csv
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def read(name, fallback=None):
    p = BASE / name
    return json.loads(p.read_text()) if p.exists() else fallback


def fmt(value):
    if value is None:
        return '—'
    if isinstance(value, float):
        return f'{value:.3f}'
    return str(value)


def table(headers, rows):
    return '<table><thead><tr>' + ''.join(f'<th>{html.escape(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{html.escape(fmt(v))}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table>'


def figure(name, caption):
    return f'<figure><a href="figures/{name}.png"><img src="figures/{name}.png" alt="{caption}"></a><figcaption>{caption}　<a href="figures/{name}.pdf">PDF</a></figcaption></figure>'


def build():
    aggregate = read('vmd/raw_only/aggregate.json')
    by_key = {(r['kind'],r['modes'],r['iterations']):r for r in aggregate}
    realrows = []
    for k,r in [(3,4),(3,32),(4,4),(5,4),(5,32),(8,32)]:
        a = by_key['real',k,r]
        realrows.append([k,r,a['mean_abs_difference_ls_band_bpm'],f"{a['agreement_ls_band_within_1bpm']:.1%}"])
    diagnostics = read('vmd/diagnostics_aggregate.json')
    initrows = [[r['initial_centers'],r['mean_abs_difference_ls_main_input_bpm']] for r in diagnostics
                if r['padding']=='zero' and r['iterations']==4]
    ls = read('lomb/accuracy_summary.json',[])
    ls_map = {r['subcarriers']:r for r in ls}
    with (BASE/'vmd/raw_only/sweep.csv').open() as f:
        vmd_raw = [r for r in csv.DictReader(f) if r['kind']=='real' and r['modes']=='3' and r['iterations']=='4']
    with (BASE/'lomb/accuracy.csv').open() as f:
        ls_raw = {(r['window_id'],int(r['subcarriers'])):r for r in csv.DictReader(f)}
    candidate_raw = {r['case']:r for r in read('vmd/diagnostics.json')
                     if r['padding']=='zero' and r['iterations']==4 and r['initial_centers']=='[8, 16, 24]'}
    pipeline_rows = [dict(window_id=r['case'],vmd_default_bpm=float(r['bpm']),
                          vmd_candidate_bpm=candidate_raw[r['case']]['bpm'],
                          ls_8sc_bpm=float(ls_raw[r['case'],8]['bpm']),
                          ls_32sc_bpm=float(ls_raw[r['case'],32]['bpm'])) for r in vmd_raw]
    with (HERE/'raw_pipeline_comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(pipeline_rows[0]));writer.writeheader();writer.writerows(pipeline_rows)
    proof = read('lomb/proof_summary.json',[])
    compile_records = read('lomb/compile_summary.json',[])
    proofmap = {r['subcarriers']:r for r in proof}
    incomplete = [r for r in proof if r['proof_status'] != 'verified']
    resource_note = ('<p class="note">32本は8 GiBのNodeヒープ上限で鍵生成がメモリ不足となった。'
                     '12 GiBでの再試行も30分の上限内に完了せず、証明生成・検証時間は未取得（—）。'
                     '32本の実データ推定値とwitness照合は完了している。これは設定した環境・制限での結果であり、'
                     '回路が原理的に証明不可能という意味ではない。<a href="../lomb/failures/attempts.json">試行記録</a></p>') if incomplete else ''
    timingrows = []
    for c in compile_records:
        p = proofmap.get(c['subcarriers'],{})
        timingrows.append([c['subcarriers'],c['constraints'],c['compile_seconds'],p.get('setup_seconds'),
                           ls_map[c['subcarriers']]['witness_seconds_mean'],p.get('prove_seconds_median'),p.get('verify_seconds_median'),
                           p.get('proof_status','測定中')])
    validations = read('vmd/circuit_validation.json',[])
    quality = [r for r in read('common/manifest.json')['files'] if Path(r['source']).name.startswith('csi_')]
    content = []
    def section(title,body):
        content.append(f'<section><h2>{title}</h2>{body}</section>')
    section('今回の結果', '''<p class="lead">VMDは反復数を増やすだけでは改善しない。初期中心の配置を変える候補が得られた。</p>
<p>実CSI 8件で、既定K=3・R=4のLS参照値との差は平均10.657 BPM。K=4・R=4では1.108 BPMとなった。
K=3・R=4のまま初期中心を[8,24,48]から[8,16,24]へ変えても差が小さくなり、同じ制約数で試せる改善候補となった。</p>
<p>Lomb–Scargleは1〜32本を比較。実CSIで本数を増やしたときの全サブキャリア参照値との一致は非単調だった。各構成の証明生成時間を測定し、完了分を表に記録した。</p>
<p class="note">今回は正解データなしで評価する。この報告の「差」は手法間の一致度であり、呼吸数の正解誤差ではない。本編はRaw実データの結果に限定する。</p>''')
    section('実験条件と評価指標', '''<p>10月19日資料の「VMDモード数・反復数」「LSサブキャリア数」を分けて検証した。元のRawデータと本番コードは変更していない。</p>''' + table(
        ['項目','VMD近似回路','Lomb–Scargle E2E回路'],[
            ['元データ','Raw直下8収録・冒頭48秒','同じ8収録・冒頭48秒'],
            ['入力','時刻補間→SNR選択→filter→PCA→2 Hz','Tx0/Rx0固定の複素CSIと元の記録時刻'],
            ['点数','96観測点＋32点ゼロ埋め→128点整数','64観測点を抽出・I/Q量子化'],
            ['変える条件','K=1,2,3,4,5,8 / R=1,2,4,8,16,32','1,2,4,8,16,32本（入れ子選択）'],
            ['固定条件','DFT、整数更新、全域最大ピーク規則','32周波数bin、同じ32候補による量子化スケール'],
            ['実データの参照','同じ128点波形上のSciPy LS','同じ64点・同じ周波数gridの浮動小数点LS']]) +
        '''<p>LSの既存エッジ入力は平坦化したCSI配列から等間隔8列を選ぶ。今回は本数の影響を切り分けるため、同じTx/Rx対に固定し、既存列を残したまま追加する入れ子選択とした。したがって、この8本条件は旧入力選択をそのまま再現した条件ではない。旧方式の補足比較はlomb/legacy8_sensitivity.csvに保存した。</p><p class="note">VMD表のLS参照と、生CSIを入力するLS回路は異なる。前処理・点数・周波数grid・ピーク選択規則が違うため、二つの表を同条件での方式の勝敗として解釈しない。</p>''')
    section('同じ実測収録に対する両回路の推定値',table(
        ['収録','VMD既定','VMD初期中心変更','LS 8本','LS 32本'],[
            [r['window_id'].removesuffix('_w0'),r['vmd_default_bpm'],r['vmd_candidate_bpm'],r['ls_8sc_bpm'],r['ls_32sc_bpm']] for r in pipeline_rows]) +
        '<p>単位BPM。同じ48秒区間を起点とした、前処理を含むパイプライン全体の出力比較。VMDは全域最大ピーク、LSの表示BPMは正常帯域内ピークであり、LSの値が範囲内に入ることだけでは正しさを評価できない。LSには別に全域ピーク・正常判定出力もある。<a href="raw_pipeline_comparison.csv">表のCSV</a></p>')
    section('Rawデータの時刻品質', figure('dataset_rates','実時刻から計算した保持フレームの平均レート') + table(
        ['収録','長さ(s)','保持行数','平均Hz','最大間隔(s)'],[
            [Path(r['source']).stem,r['duration_seconds'],r['retained_rows'],r['effective_average_hz'],r['dt_max_seconds']] for r in quality]) +
        '<p>全8収録が64秒より短い。VMDの末尾16秒は観測値ではない。100 Hzへの補間は新しい情報を追加せず、疎な収録と大きい欠測間隔の限界は残る。sample_dataの2記録は補足データとして保存し、主表の8件には混ぜていない。</p>')
    section('VMD：モード数・反復数の比較',figure('vmd_real','同じ入力波形のLSとの平均絶対差。正解誤差ではない。') +
        table(['K','R','平均絶対差(BPM)','1 BPM以内の一致率'],realrows) +
        '<p>36条件のスイープは回路と同じ整数演算を実装したPython参照で実行した。代表4構成×実8件で実回路witnessと全最終係数・中心・出力を照合した。36構成すべてのGroth16証明を生成した実験ではない。</p><p>既定K=3では反復数だけを増やしても一致が良くならない。K=4以降の初期中心にはbin16が追加されるため、Kの効果と初期中心の効果が混在している。</p>' +
        figure('vmd_real_estimates','収録ごとの推定値。高いBPMが正しいかはGTなしでは判断できない。'))
    section('VMD：初期中心の感度分析',figure('vmd_initialization','モード数3・反復4・ゼロ埋めを固定した比較') +
        table(['初期中心(bin)','同じ128点LSとの平均絶対差(BPM)'],initrows) +
        '<p>この表は前のスイープと同じ128点LSを参照する。[8,16,24]は既定と同じ340,734制約。ただし、この8記録に基づく候補選定であり、独立データでの検証は未実施。低域へ中心を寄せる変更なので、高い周波数を含む記録での評価も必要。</p>')
    section('VMD：保持される周波数成分',figure('vmd_spectrum_example','同じ実データ入力に対する既定と候補のモードスペクトル') + '<p>この例では入力の最大ピーク付近を既定配置のモードが十分に保持せず、別の高域ピークを選ぶ。候補は低域を保持する。どちらが実際の呼吸かは正解データなしでは決められない。</p>')
    section('Lomb–Scargle：本数と一致度',figure('lomb_agreement','同条件LSとの差と、同一アンテナ対の全tones LSとの差を分離') +
        table(['本数','実データ：全tonesとの差(BPM)','実データ：同条件bin一致率'],[
            [r['subcarriers'],r['absolute_difference_all_sc_bpm_mean'],f"{r['same_sc_bin_agreement_mean']:.1%}"] for r in ls]) +
        '<p>同条件の浮動小数点LSと整数回路の差は小さい一方、どのサブキャリアが選ばれるかで実データ推定値は変化する。本数を増やせば常に全tones参照へ近づくわけではない。全tones参照も呼吸の正解ではない。</p>')
    section('Lomb–Scargle：実回路の処理時間',table(
        ['本数','制約数','compile(s)','setup(s)','witness平均(s)','prove中央値(s)','verify中央値(s)','状態'],timingrows) +
        '<p>witnessは各本数で実8収録の計算時間平均（WASM読込・Node起動等を除く）。prove/verifyは代表1収録に対する3回の中央値。32本もwitness計算は完了している。</p>' +
        (figure('lomb_proof_time','Groth16証明生成：完了構成の3回の中央値と最小〜最大') if (HERE/'figures/lomb_proof_time.png').exists() else '') + resource_note +
        '<p>Apple M4 Pro・RAM 24 GiB・macOS 26.6.2上の測定。エッジ端末の実測ではない。compile/setupと鍵contributionは回路構成ごとの準備であり、毎回の推定時間には加えない。LSはCircom O2でコンパイル。ローカルで新たなcontributionを加えた実験用鍵を使用。本番配布用の鍵管理・セレモニー検証は今回の範囲外。共有マシンのwall-clock時間なので微小差の順位には使わない。</p>')
    section('検証と保存したコード',table(['VMD回路','制約数','最終係数・中心の一致'],[
        [r['name'],r.get('constraints_total'),r['all_final_spectra_and_centers_match']] for r in validations]) +
        '''<p>VMDはPython整数参照と実際のWASM witnessを照合した。LSも各本数の回路witnessと整数参照を照合し、Groth16 proofをローカルverifyする。入力データのSHA256・時刻品質・環境・再実行コマンドを各ディレクトリに保存した。</p>
<p><a href="../common/validation.json">入力検査</a> · <a href="../vmd/README.md">VMD再現手順</a> · <a href="../lomb/README.md">LS再現手順</a></p>
<p>コード画像は元ファイルから行番号付きで生成。HTMLを開いて撮り直すこともできる。</p>
<figure><a href="code_vmd_circuit.html"><img src="code_vmd_circuit.png" alt="VMD回路の初期中心"></a><figcaption>実際にコンパイル・witness照合した初期中心変更候補</figcaption></figure>
<figure><a href="code_lomb_circuit.html"><img src="code_lomb_circuit.png" alt="LS回路の32本構成"></a><figcaption>64点・32サブキャリア・32周波数binの回路構成</figcaption></figure><p>追加の撮影用コード：<a href="code_vmd.html">VMD整数参照</a> / <a href="code_lomb.html">LS入力条件の固定</a></p>''')
    if (HERE/'trace_viewer.html').exists():
        section('追加：公開中間値の波形', '''<p><a href="trace_viewer.html"><b>処理段階・反復・サブキャリアを切り替える波形ビューアを開く</b></a></p>
<p>同じ実測収録 csi_20260526_034004 の診断用回路を別に作成した。VMDは入力波形・DFT・全4反復のモード係数と中心を公開。LSはI/Q・振幅二乗・平均除去・sin/cos基底・射影・スコアの分子/分母を公開する。</p>
<p>実際の公開出力から値を取り出し、両診断回路でGroth16証明を生成・検証した。中間値1要素を改ざんすると同じ証明が拒否されることも確認した。VMDの逆DFT表示とLSの分子/分母の割り算は回路外の描画処理である。</p>
<p class="note">公開中間値は入力波形の情報を明らかにする。通常回路・鍵を変更せず、独立した診断回路で中間値を公開している。鍵と処理時間も通常回路から分離した。</p>
<p>公開出力への接続コード：<a href="code_debug_vmd.html">VMD撮影用HTML</a> / <a href="code_debug_vmd.png">VMD PNG</a> / <a href="code_debug_lomb.html">LS撮影用HTML</a> / <a href="code_debug_lomb.png">LS PNG</a></p>
<figure><img src="trace_figures/vmd_iterations.png" alt="VMD反復ごとのモード波形表示"><figcaption>実際の公開モード係数から、表示側で逆DFTした波形</figcaption></figure>
<figure><img src="trace_figures/lomb_stages.png" alt="LS段階ごとの公開値"><figcaption>LS回路の選択サブキャリアにおける段階ごとの数値</figcaption></figure>
<p><a href="../diagnostics/vmd/README.md">VMD診断の再実行</a> / <a href="../diagnostics/lomb/README.md">LS診断の再実行</a></p>''')
    section('報告時に伝える結論と次の実験', '''<ol>
<li>VMDは「回数不足」だけでは説明できない。初期中心[8,16,24]を、正解付きの別収録で検証する。</li>
<li>LSは本数増の計算コストと、実データ推定値への効果を分けて示す。実呼吸の最適本数は未確定。</li>
<li>呼吸ベルトなどの同期GT、64秒以上の収録、記録時刻に基づく処理をそろえ、正常・異常・体動条件で評価する。</li>
<li>今回の結果を根拠に本番回路の設定を自動変更していない。候補回路・評価コードはresearch配下に独立して保存した。</li></ol>''')
    document = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>2026-10-26 CSI呼吸推定回路の比較実験</title><style>
*{box-sizing:border-box} body{margin:0;background:#edf1f5;color:#192c3d;font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif;line-height:1.8}
header,section{max-width:1160px;margin:28px auto;padding:40px 52px;background:white}
header{border-top:8px solid #256b90}h1{font-size:34px;line-height:1.5}h2{font-size:28px;border-bottom:2px solid #256b90;padding-bottom:14px;line-height:1.5}
p,li{font-size:18px}.lead{font-size:24px;font-weight:600}.note{border-left:5px solid #b56a2f;padding:12px 20px;background:#fff8ed}
table{border-collapse:collapse;width:100%;font-size:15px;margin:24px 0}th,td{text-align:left;border-bottom:1px solid #d3dde4;padding:10px 12px}th{background:#edf4f8}
figure{margin:28px 0}img{max-width:100%;height:auto;display:block;margin:auto}figcaption{font-size:14px;color:#486273;margin-top:12px}a{color:#176d9e}code{font-family:Menlo,monospace}
@media print{body{background:white}header,section{margin:0;max-width:none;break-before:page;padding:20px}figure,table{break-inside:avoid}}
</style><header><p>修士研究 / 2026年10月26日</p><h1>CSI呼吸推定回路の<br>パラメータ比較実験</h1><p>VMDのモード数・反復数・初期中心<br>Lomb–Scargleのサブキャリア本数・処理時間</p><p><a href="../README.md">再現とファイル一覧</a> · 図はクリックで原寸PNG、コードはクリックで撮影用HTMLを開きます。</p></header>'''
    (HERE/'report_details.html').write_text(document+'\n'.join(content)+'</html>',encoding='utf-8')
    summarytable = table(['LS 本数','制約数','証明時間の中央値(s)','全tones LSとの差(BPM)'],[
        [c['subcarriers'],f"{c['constraints']:,}",proofmap.get(c['subcarriers'],{}).get('prove_seconds_median'),
         ls_map.get(c['subcarriers'],{}).get('absolute_difference_all_sc_bpm_mean')] for c in compile_records])
    summary = '''<!doctype html><html lang="ja"><meta charset="utf-8"><title>進捗報告要約</title><style>
*{box-sizing:border-box}body{width:1200px;height:900px;margin:0;padding:36px 52px;background:white;color:#1b2e3c;font-family:-apple-system,"Hiragino Sans",sans-serif}
h1{font-size:36px;margin:0 0 16px;border-bottom:4px solid #296c8d;padding-bottom:16px}h2{font-size:26px;margin:22px 0 8px}
p{font-size:22px;line-height:1.65;margin:8px 0}table{border-collapse:collapse;width:100%;font-size:21px;margin-top:18px}th,td{padding:9px 18px;border-bottom:1px solid #ccd7df;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#edf4f7}.note{font-size:18px;color:#586b79;margin-top:20px}.footer{font-size:16px;color:#647885;margin-top:16px}</style>
<h1>CSI呼吸推定回路の比較実験 <span style="font-size:22px">2026/10/26</span></h1>
<h2>VMD：反復増より初期中心の影響が大きい</h2>
<p>同一PCA波形LSとの差（実8件）：K3/R4 <b>10.657</b> → K3/R32 <b>11.145 BPM</b><br>
K4/R4、またはK3/R4＋中心[8,16,24]で <b>1.108 BPM</b></p>
<p style="font-size:19px">初期中心変更のK3候補は既定と同じ340,734制約。別の実測記録での検証が必要。</p>
<h2>Lomb–Scargle：サブキャリア数と証明コスト</h2>'''+summarytable+'''
<p class="note">実CSI 8収録を使用。正解呼吸数なし：LSとの差は一致度であり、正解誤差ではない。<br>
証明時間はApple M4 Pro / RAM 24 GiB、完了構成3回の中央値。setup等は除外。</p>
<div class="footer">詳細・図・再現コード：zkp/experiments/2026-10-26/　　実データの生体精度とエッジ実機時間は未確定</div></html>'''
    if incomplete:
        summary=summary.replace('詳細・図・再現コード：zkp/experiments/2026-10-26/　　実データの生体精度とエッジ実機時間は未確定', '32本：8 GiB heapでOOM、12 GiBでsetup 30分上限。推定値・witness照合は完了。')
    (HERE/'summary.html').write_text(summary,encoding='utf-8')
    from make_story import build_story
    build_story()
    print(HERE/'report.html')


if __name__ == '__main__':
    build()
