from pathlib import Path,PurePosixPath
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
import hashlib,json,posixpath,shutil,io
ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'output/pptx/2026_10_26_進捗_黒川.pptx'
TARGET=Path('/Users/ryunosukekurokawa/Documents/class/lab/M2/進捗/2026_10_26/2026_10_26_進捗_黒川.pptx')
BACKUP=TARGET.with_name(TARGET.stem+'_編集前バックアップ.pptx')
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
with ZipFile(OUT) as z,ZipFile(BACKUP) as old:
 names=set(z.namelist());texts=[]
 for n in names:
  if n.endswith(('.xml','.rels')):E.fromstring(z.read(n))
  if n.startswith(('ppt/slideMasters/','ppt/slideLayouts/','ppt/theme/')):assert z.read(n)==old.read(n)
  if n.endswith('.rels'):
   base='' if n=='_rels/.rels' else str(PurePosixPath(n).parent.parent)
   for r in E.fromstring(z.read(n)):
    if r.get('TargetMode')!='External':assert posixpath.normpath(posixpath.join(base,r.get('Target'))) in names,(n,r.get('Target'))
 for i in range(1,11):
  root=E.fromstring(z.read(f'ppt/slides/slide{i}.xml'));texts+=root.xpath('//a:t/text()',namespaces=ns)
  ids=root.xpath('//p:cNvPr/@id',namespaces=ns);assert len(ids)==len(set(ids))
 for i in range(1,4):
  root=E.fromstring(z.read(f'ppt/charts/chart{i}.xml'))
  assert root.find('c:externalData',ns) is not None
  with ZipFile(io.BytesIO(z.read(f'ppt/embeddings/data{i}.xlsx'))) as book:
   assert book.testzip() is None
   for n in book.namelist():E.fromstring(book.read(n))
 assert '正解呼吸数なし → 参照手法との一致度を評価' in texts
 assert any('計17件' in t for t in texts)
 assert not any('合計 30' in t for t in texts)
 assert z.testzip() is None
# Guard against replacing work the user edited while this task ran.
assert hashlib.sha256(TARGET.read_bytes()).digest()==hashlib.sha256(BACKUP.read_bytes()).digest(),'Target changed during editing'
shutil.copy2(OUT,TARGET)
assert TARGET.read_bytes()==OUT.read_bytes()
p=Path(__file__).with_name('validation.json');v=json.loads(p.read_text());v.update({'all_xml_and_relationships_valid':True,'embedded_chart_workbooks_valid':3,'quicklook_individual_slide_previews_checked':10,'native_powerpoint_visual_check':False,'original_path_updated':str(TARGET),'backup':str(BACKUP),'final_sha256':hashlib.sha256(TARGET.read_bytes()).hexdigest()});p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(v,ensure_ascii=False,indent=2))
