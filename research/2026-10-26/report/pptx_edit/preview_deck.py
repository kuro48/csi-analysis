from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E,html
import subprocess,tempfile,concurrent.futures,json
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[4]
SOURCE=ROOT/'output/pptx/2026_10_26_進捗_黒川.pptx'
OUT=ROOT/'tmp/pptx_checked';OUT.mkdir(exist_ok=True)
with ZipFile(SOURCE) as z:parts={n:z.read(n) for n in z.namelist()}
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
def page(i):
 d=OUT/f'page{i:02d}';d.mkdir(exist_ok=True);r=E.fromstring(parts['ppt/presentation.xml']);ids=r.find('p:sldIdLst',ns)
 for j,e in enumerate(list(ids)):
  if j!=i-1:ids.remove(e)
 f=d/'slide.pptx'
 with ZipFile(f,'w',ZIP_DEFLATED) as z:
  for n,b in parts.items():z.writestr(n,E.tostring(r) if n=='ppt/presentation.xml' else b)
 subprocess.run(['qlmanage','-p','-o',str(d),str(f)],check=True,capture_output=True)
 preview=d/'slide.pptx.qlpreview';doc=preview/'Preview.html';root=html.fromstring(doc.read_text())
 for im in root.xpath('//img'):
  src=im.get('src')
  if src.endswith('.pdf'):
   stem=preview/Path(src).stem
   subprocess.run(['pdftoppm','-singlefile','-scale-to','1500','-png',str(preview/src),str(stem)],check=True,capture_output=True)
   im.set('src',stem.name+'.png')
 style=E.SubElement(root.find('head'),'style');style.text='body{margin:0!important;background:white!important}div.slide{margin:0!important;box-shadow:none!important;width:720px!important;height:540px!important}'
 doc.write_bytes(html.tostring(root))
 with tempfile.TemporaryDirectory(prefix='csi-pptx-render-') as profile:
  subprocess.run(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--headless','--disable-gpu','--no-first-run','--no-default-browser-check',f'--user-data-dir={profile}','--hide-scrollbars','--window-size=720,540','--force-device-scale-factor=2',f'--screenshot={OUT / ("page%02d.png"%i)}',doc.as_uri()],check=True,capture_output=True,timeout=60)
 return i
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: print(list(pool.map(page,range(1,11))))
contact=Image.new('RGB',(1530,1160),'#ddd')
for i in range(1,11):
 im=Image.open(OUT/f'page{i:02d}.png');im.thumbnail((380,285));contact.paste(im,(((i-1)%3)*510,((i-1)//3)*290))
contact.save(OUT/'contact.png')
