"""Readable purpose/action/result narrative, alternating explanation and measured figures."""
import html
import json
from pathlib import Path
from PIL import Image
HERE=Path(__file__).resolve().parent
BASE=HERE.parent

def build_story():
    def read(p):return json.loads((BASE/p).read_text())
    a={(x['modes'],x['iterations']):x for x in read('vmd/raw_only/aggregate.json') if x['kind']=='real'}
    diff=lambda k,r:f"{a[k,r]['mean_abs_difference_ls_band_bpm']:.3f}"
    ls=read('lomb/accuracy_summary.json'); proofs=read('lomb/proof_summary.json')
    good=[p for p in proofs if p['proof_status']=='verified']
    sections=[]
    def figure(path,caption):
        with Image.open(HERE/path) as im: width,height=im.size
        return f'<figure><a href="{path}"><img src="{path}" alt="{html.escape(caption)}" width="{width}" height="{height}"></a><figcaption>{caption}</figcaption></figure>'
    def section(id,title,purpose,action,visual,result,limit=''):
        sections.append(f'''<section id="{id}"><h2>{title}</h2>
<p><b>目的</b>{purpose}</p><p><b>行ったこと</b>{action}</p>
{visual}
<div class="result"><h3>結果・分かったこと</h3><p>{result}</p></div>
{f'<p class="limit">{limit}</p>' if limit else ''}</section>''')
    section('vmd','1. VMD：モード数・反復数を増やすと変わるか',
        '回路内VMDの推定値がLS参照から大きく離れる状況に対し、<strong>分解する成分の数や計算回数の不足で説明できるか</strong>を調べる。',
        '同じ実データ8収録で、モード数6通り × 反復数6通りの計36設定を比較した。モードは「信号を分けた各周波数成分」、反復は「その分け方を更新する計算回数」を指す。',
        figure('brief/vmd_sweep.png','各セルは、同じ入力波形のLS参照との平均絶対差（BPM）。小さいほど参照と近い。'),
        f'3モードでは、反復4回の差 <strong>{diff(3,4)} BPM</strong> に対し、32回でも <strong>{diff(3,32)} BPM</strong>。反復を増やすだけでは差は小さくならなかった。一方、4モード・4回では <strong>{diff(4,4)} BPM</strong> となった。',
        'ただし、4モードにすると初期中心も1つ増える。「モード数の効果」と「最初に置く周波数の効果」を、この比較だけでは分けられない。')
    section('centers','2. VMD：最初に置く周波数の影響を調べる',
        'モードを増やしたことではなく、<strong>初期中心の配置</strong>が結果を変えた可能性を調べる。初期中心は、各モードが分解を始める周波数の目安。',
        '3モード・4反復を固定し、初期中心のbin番号を <code>[8,24,48]</code> から <code>[8,16,24]</code> へ変更した。これは約 <code>[7.5,22.5,45]</code> から <code>[7.5,15,22.5]</code> BPMへの変更。',
        figure('brief/vmd_centers.png','左2本は既定の初期中心。右端はモード数と反復数を変えず、初期中心だけを変更した条件。'),
        '初期中心だけの変更でも、LS参照との差は <strong>10.657 → 1.108 BPM</strong> に小さくなった。制約数は既定と同じ <strong>340,734</strong>。今回の8収録では、計算回数を増やすよりも初期配置を見直す候補が得られた。',
        'この8収録を使って選んだ候補であり、真の呼吸数に近づいたとはまだ言えない。未使用の収録と正解呼吸数を使った確認が必要。')
    section('ls-estimate','3. Lomb–Scargle：本数を増やすと推定値はどう変わるか',
        '利用するサブキャリアを増やしたときに、<strong>推定値が参照値へ近づくか</strong>を調べる。',
        '同じ8収録について、1・2・4・8・16・32本を比較した。同じ送受信アンテナの組を使い、既に選んだサブキャリアを残したまま本数を増やした。',
        figure('brief/ls_difference.png','参照は、同じアンテナ対の全サブキャリアを使った浮動小数点LS。呼吸の正解値ではない。'),
        f'全サブキャリア参照との差は、1本で <strong>{ls[0]["absolute_difference_all_sc_bpm_mean"]:.3f} BPM</strong>、32本で <strong>{ls[-1]["absolute_difference_all_sc_bpm_mean"]:.3f} BPM</strong>。ただし、途中で差が大きくなる条件もあり、<strong>本数を増やせば毎回改善するわけではなかった</strong>。',
        '別の確認として、同じサブキャリア集合・点数・周波数候補の浮動小数点LSと比べると、全48条件で推定binと選択サブキャリアが一致した。これは実装間の一致であり、生体情報としての精度の保証ではない。')
    section('ls-time','4. Lomb–Scargle：本数を増やすと証明は重くなるか',
        '推定値への効果と合わせて、<strong>証明生成の時間がどの程度増えるか</strong>を調べる。',
        '各本数の回路を作成し、代表1収録で証明生成・検証を3回ずつ実行した。鍵生成などの準備時間と、毎回の証明生成時間は分けて記録した。',
        figure('brief/ls_proof.png','Apple M4 Pro・RAM 24 GiBでの実測。棒は3回の中央値、線は最小〜最大。鍵生成・witness・検証時間を除く。'),
        f'1本の証明生成は <strong>{good[0]["prove_seconds_median"]:.2f}秒</strong>、16本では <strong>{good[-1]["prove_seconds_median"]:.2f}秒</strong>。1〜16本の計15証明はすべて検証に成功した。<strong>本数増には証明生成時間の増加が伴った</strong>。',
        '32本は推定計算・witness生成まで成功したが、鍵生成がNodeの8 GiB上限でメモリ不足、12 GiBでの再試行も30分上限に達した。32本の証明生成時間は未取得。今回の時間はエッジ端末での実測ではない。')
    section('vmd-trace','5. VMD：最終結果だけでなく、途中の変化を見る',
        '最終BPMだけでは分からない、<strong>各反復で残る成分や中心周波数の変化</strong>を確認できるようにする。',
        '診断用の別回路に、入力・DFT係数・各反復のモード係数・中心を公開出力として追加した。代表収録を3モード・4反復で処理し、証明も生成した。',
        figure('brief/vmd_trace.png','同じ収録の反復1回目と4回目。公開した周波数係数から、表示側で逆DFTしたモード波形。灰色は観測外のゼロ埋め区間。'),
        '代表収録の中心binは <code>[8,24,48] → [8,24,47] → [8,24,46] → [8,24,46] → [8,24,46]</code>。<strong>中心は2回目以降変わらなかった</strong>。途中の係数・波形を比較できるようになり、反復追加の効果を調べる材料が得られた。',
        '中心が同じでも、全モード係数が同じとは限らない。この例だけで全収録の原因は断定しない。逆DFTは回路内の処理ではなく表示用の変換。')
    section('ls-trace','6. Lomb–Scargle：処理段階ごとの数値を見る',
        '入力から最終周波数を選ぶまでの、<strong>どの処理で数値がどう変わるか</strong>を確認できるようにする。',
        'I/Q、振幅二乗、平均除去、sin/cos基底、射影、スコアの分子・分母を公開出力へ追加した。VMDと同じ代表収録を、8本の診断回路で処理した。',
        figure('brief/ls_trace.png','回路が選択したSC 7（元tone 32）の例。時間波形から周波数ごとのスコアへ進む。'),
        '段階ごとの公開値から、<strong>振幅二乗 → 平均除去 → 周波数スコア</strong>を図にできた。両診断回路とも証明検証に成功し、公開中間値を1つ変えると同じ証明が拒否されることも確認した。<a href="trace_viewer.html">全段階を切り替える波形ビューア</a>で詳細を見られる。',
        'LSスコアの分子÷分母は表示側の計算。診断回路では入力情報が公開されるため通常回路と分離した。VMDとLSは前処理・点数・ピーク選択が違い、この代表例のBPMだけでは方式の優劣を判断できない。')
    doc='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>今回の目的・実施内容・結果 | CSI呼吸推定回路</title><style>
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:#202f3a;background:#f1f3f5;font:18px/1.85 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif}
header,section{max-width:1060px;margin:24px auto;background:white;padding:40px 54px}header{border-top:6px solid #296b8c}h1{font-size:34px;line-height:1.55;margin:10px 0 22px}h2{font-size:27px;line-height:1.55;margin:0 0 25px}h3{font-size:20px;margin:0 0 8px}p{margin:15px 0}p>b{display:block;color:#256b90;font-size:16px}strong{font-weight:650}a{color:#19698e}nav{font-size:16px;line-height:2.1}figure{margin:30px 0}figure img{width:100%;height:auto;display:block}figcaption{color:#52616d;font-size:14px;line-height:1.65;margin-top:10px}.result{border-left:4px solid #296b8c;padding:12px 22px;background:#f3f7fa}.result p{margin:0}.limit{font-size:15px;color:#535e67}.context{padding:15px 20px;background:#fff8ee;border-left:4px solid #b88650}code{font-family:Menlo,monospace;font-size:.9em}table{border-collapse:collapse;width:100%;font-size:16px}th,td{padding:12px;text-align:left;border-bottom:1px solid #d7dfe4}th{background:#f3f6f8}.small{font-size:15px;color:#53616c}
@media(max-width:700px){header,section{padding:26px 22px;margin:12px}h1{font-size:28px}h2{font-size:23px}body{font-size:17px}table{font-size:14px}}
@media print{body{background:white}header,section{margin:0;max-width:none;break-before:page;padding:24px}figure,.result{break-inside:avoid}nav{display:none}}
</style><header><p class="small">修士研究 / 2026年10月26日</p><h1>今回、何を確かめるために<br>何を行い、何が分かったか</h1>
<p class="context"><strong>各比較proofの公開中間値を含めた再測定版</strong>：<a href="../remeasure_public/report.html">新しい測定結果・完了状況</a> / <a href="../remeasure_public/index.html">各proofに対応する波形</a>。以下は前回までの結果で、追加公開後の新しい計時とは分けています。</p>
<p>今回の目的は、<strong>回路内VMDの推定が変わる条件</strong>と、<strong>Lomb–Scargleの本数増による効果・計算負荷</strong>を調べること。さらに、原因を追えるように回路の途中の数値を見える形にした。</p>
<div class="context"><strong>今回評価できるのは「参照手法との一致度」。真の呼吸数への精度は未評価。</strong><br>Rawの実データ8収録を使用。正解呼吸数がないため、LS参照との差を比べた。VMDの参照は同じPCA波形上のLS、LS本数比較の参照は同じアンテナ対の全サブキャリアLSで、別の基準である。</div>
<nav><a href="#vmd">VMDの設定比較</a> / <a href="#ls-estimate">LSの本数比較</a> / <a href="#ls-time">証明時間</a> / <a href="#vmd-trace">中間値の波形</a> / <a href="#scope">完了範囲</a></nav></header>'''
    doc+='\n'.join(sections)
    doc+='''<section id="scope"><h2>今回の到達点と、まだ言えないこと</h2>
<table><thead><tr><th>項目</th><th>今回完了した範囲</th></tr></thead><tbody>
<tr><td>VMDの設定比較</td><td>実8件×36設定の整数参照計算。代表4構成×8件で実回路witnessと最終係数・中心・出力を照合。</td></tr>
<tr><td>通常LS</td><td>実8件×6本数のwitness照合。1・2・4・8・16本は各3回、計15件の証明生成・検証成功。32本の証明は未生成。</td></tr>
<tr><td>公開中間値の診断</td><td>VMDとLSの代表各1件で証明生成・検証・中間値改変の拒否を確認。通常LSと合わせ計17証明。</td></tr>
</tbody></table>
<p class="small">witnessは回路内の計算値一式。witnessを生成・照合することと、Groth16証明を生成することは別。通常VMDの36設定すべてについて証明を生成したわけではない。</p>
<div class="result"><h3>報告で伝える結論</h3><p>VMDは反復数だけでなく<strong>初期中心の配置を見直す候補</strong>が得られた。LSは本数増によって<strong>証明時間が増えた一方、参照値との一致は単調には改善しなかった</strong>。中間値の公開により、今後は最終BPMだけでなく処理途中から挙動を調べられる。</p></div>
<p><b>次に必要なこと</b>正解呼吸数付き・未使用の収録で候補を評価する。今回の8件に合う設定が、別の収録でも良いとは限らない。32本の鍵生成条件と、エッジ実機での処理時間も別途確認する。</p>
<p class="small"><a href="report_details.html">全測定表・入力条件・コード画像を含む詳細版</a> / <a href="trace_viewer.html">公開中間値ビューア</a> / <a href="../README.md">再現手順・ファイル一覧</a></p></section></html>'''
    (HERE/'report.html').write_text(doc)

if __name__=='__main__':build_story()
