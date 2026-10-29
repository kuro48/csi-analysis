from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
OUT=ROOT/'output/pdf/2026_10_26_進捗_黒川.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
for name,weight in [('JP','Regular'),('Light','Light')]:
 pdfmetrics.registerFont(TTFont(name,str(Path.home()/f'Library/Fonts/NotoSansJP-{weight}.ttf')))
c=canvas.Canvas(str(OUT),pagesize=(720,540));c.setTitle('修士研究 進捗報告 - 2026年10月26日');c.setAuthor('黒川龍之介')
page=0

def text(s,x,y,size=19,font='JP',color='#222222'):
 c.setFillColor(color);c.setFont(font,size);c.drawString(x,540-y,s)
def start(title):
 global page
 page+=1;text(title,25,77,32,'Light')
def bullet(s,y=120):
 text('•',25,y);text(s,45,y)
def foot(s): text(s,30,495,11,color='#666666')
def image(p,x,y,w,h):
 im=ImageReader(str(p));iw,ih=im.getSize();scale=min(w/iw,h/ih);dw,dh=iw*scale,ih*scale
 c.drawImage(im,x+(w-dw)/2,540-y-dh,width=dw,height=dh,mask='auto')
def end():
 text(str(page),657,518,9,color='#777777');c.showPage()

page+=1
c.setFont('Light',46);c.drawCentredString(360,292,'修士研究')
c.setFont('JP',22);c.drawCentredString(360,244,'黒川龍之介')
c.setFont('JP',15);c.drawCentredString(360,205,'2026年10月26日');end()

start('今週の作業')
bullet('VMDのモード数・反復数による変化を比較',132)
text('モード数 1 / 2 / 3 / 4 / 5 / 8、反復数 1 / 2 / 4 / 8 / 16 / 32',62,168,16)
bullet('Lomb-Scargleのサブキャリア本数を比較',232)
text('1 / 2 / 4 / 8 / 16 / 32本の推定値・証明生成時間',62,268,17)
bullet('回路の中間値を公開し、波形を可視化',332)
text('実データ8収録の冒頭48秒を使用',45,416,19)
text('正解呼吸数なし → 参照手法との一致度を評価',45,451,19)
foot('VMD：96点＋32点ゼロ埋め ／ LS：実時刻64点。前処理・探索帯域は異なる。');end()

start('VMDのモード数・反復数の比較')
bullet('既定の3モードでは、反復数を増やしても改善せず',122)
image(HERE/'vmd_sweep.png',35,150,650,322)
foot('実8件・同一128点波形のLSとの差。36設定は整数参照、代表4構成×8件を実witness照合。');end()

start('VMDの初期中心の比較')
bullet('初期中心を [8,24,48] → [8,16,24] に変更',120)
bullet('3モード・4反復のまま、LSとの差が小さくなった',151)
image(HERE/'vmd_centers.png',38,175,644,292)
foot('初期中心変更は同じ340,734制約。正解誤差ではなく、別収録での検証が必要。');end()

start('Lomb-Scargleのサブキャリア数の比較')
bullet('本数を増やしても、参照値との差は一様に小さくならない',121)
image(HERE/'ls_difference.png',38,153,644,310)
foot('実8件・同じTx/Rx対の全tone LSが参照。同一SC集合の浮動LSと全48条件でbin・選択SCが一致。');end()

start('Lomb-Scargleの証明生成時間')
bullet('1〜16本の各3回、計15件の証明生成・検証が成功',120)
image(HERE/'ls_proof.png',38,148,644,293)
text('32本：Node上限8 GiBでメモリ不足、12 GiBでも鍵生成30分で停止',42,468,15)
foot('Apple M4 Pro / RAM 24 GiB。3回の中央値と範囲。setup・witness・verifyは除く。');end()

start('処理ごとの中間値を公開出力へ追加')
bullet('VMD：入力・DFT・各反復のモード係数・中心',120)
bullet('LS：I/Q・振幅二乗・平均除去・射影・スコアの分子/分母',153)
image(HERE.parent/'code_debug_vmd.png',45,183,630,274)
foot('VMD回路の追加コード。入力情報を公開する診断専用回路として分離し、通常回路は未変更。');end()

start('VMDの反復ごとの波形')
bullet('各反復の公開係数からモード波形を表示',120)
image(HERE/'vmd_trace.png',35,149,650,316)
foot('例：csi_20260526_034004。逆DFTは回路外の表示変換。灰色部分は観測外のゼロ埋め区間。');end()

start('Lomb-Scargleの処理ごとの波形')
bullet('回路が選択したサブキャリアの処理を確認',120)
image(HERE/'ls_trace.png',35,147,650,326)
foot('同じ収録・選択SC 7（元tone 32）。スコアは公開した分子÷分母を表示側で計算。');end()

start('証明生成の状況と今後')
bullet('中間値を公開する両診断回路の証明・検証が成功',124)
text('VMD：3モード・4反復 ／ LS：8本（各1収録）',62,160,18)
text('公開中間値を1つ変更すると、同じ証明は検証で拒否',62,195,18)
bullet('通常VMDの比較はwitness照合まで',259)
text('全36設定のGroth16証明は未生成',62,295,18)
bullet('今後',359)
text('正解付き・未使用の収録で初期中心候補を評価',62,395,18)
text('32本の鍵生成条件を見直し、エッジ実機でも計時',62,430,18)
foot('今回の通常LS 15件＋診断2件＝計17件の証明を生成・検証済み。');end()

c.save()
(HERE/'manifest.json').write_text(json.dumps({'pages':page,'page_size_points':[720,540],'output':str(OUT),'reference':'2026_10_19_進捗_黒川.pdf','main_data':'real CSI only'},ensure_ascii=False,indent=2)+'\n')
print(OUT)
