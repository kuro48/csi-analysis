"""Update the user's local deck, retaining its theme/layouts and editable slide text.
OOXML fallback: the supplied artifact runtime and document session are unavailable.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
import runpy, json, copy, io, hashlib
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
BASE=HERE.parents[1]
TARGET=Path('/Users/ryunosukekurokawa/Documents/class/lab/M2/進捗/2026_10_26/2026_10_26_進捗_黒川.pptx')
SOURCE=TARGET.with_name(TARGET.stem+'_編集前バックアップ.pptx')
OUT=ROOT/'output/pptx/2026_10_26_進捗_黒川.pptx'
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
REL='http://schemas.openxmlformats.org/package/2006/relationships';CT='http://schemas.openxmlformats.org/package/2006/content-types'
def el(tag,parent=None,**attrs):
 prefix,local=tag.split(':');e=E.Element('{'+NS[prefix]+'}'+local,**{k:str(v) for k,v in attrs.items()})
 if parent is not None:parent.append(e)
 return e
def xml(t):return E.tostring(t,xml_declaration=True,encoding='UTF-8',standalone=True)
def emu(v):return str(round(v*12700))
class Capture:
 def __init__(self,*a,**k):self.pages=[];self.items=[];self.font='JP';self.size=19;self.color='#222222'
 def setTitle(self,*a):pass
 def setAuthor(self,*a):pass
 def setFont(self,font,size):self.font=font;self.size=size
 def setFillColor(self,color):self.color=color
 def drawString(self,x,y,s):self.items.append(dict(kind='text',x=x,y=540-y,text=s,size=self.size,font=self.font,color=self.color))
 def drawCentredString(self,x,y,s):self.drawString(x-pdfmetrics.stringWidth(s,self.font,self.size)/2,y,s)
 def drawImage(self,im,x,y,width,height,**kw):self.items.append(dict(kind='image',path=str(im.fileName),x=x,y=540-y-height,w=width,h=height))
 def showPage(self):self.pages.append(self.items);self.items=[]
 def save(self):pass
canvas.Canvas=Capture
capture=runpy.run_path(str(HERE.parent/'brief/make_pdf.py'))['c']
parts={}
with ZipFile(SOURCE) as z:
 for n in z.namelist():
  if not n.startswith(('ppt/slides/','ppt/notesSlides/','ppt/media/')):parts[n]=z.read(n)
cts=E.fromstring(parts['[Content_Types].xml'])
E.SubElement(cts,'{'+CT+'}Default',Extension='jpg',ContentType='image/jpeg')
for x in list(cts):
 if x.get('PartName','').startswith(('/ppt/slides/','/ppt/notesSlides/')):cts.remove(x)
def content(path,kind):E.SubElement(cts,'{'+CT+'}Override',PartName='/'+path,ContentType=kind)
def relation(rels,rid,kind,target):E.SubElement(rels,'{'+REL+'}Relationship',Id=rid,Type=NS['r']+'/'+kind,Target=target)
def transform(parent,x,y,w,h,prefix='a'):
 t=el(prefix+':xfrm',parent);el('a:off',t,x=emu(x),y=emu(y));el('a:ext',t,cx=emu(w),cy=emu(h))
def textbox(tree,sid,s,x,y,w,h,size=19,font='JP',color='#222222'):
 sp=el('p:sp',tree);nv=el('p:nvSpPr',sp);el('p:cNvPr',nv,id=sid,name=f'Text {sid}');el('p:cNvSpPr',nv,txBox=1);el('p:nvPr',nv)
 pr=el('p:spPr',sp);transform(pr,x,y,w,h);geom=el('a:prstGeom',pr,prst='rect');el('a:avLst',geom);el('a:noFill',pr)
 tx=el('p:txBody',sp);bp=el('a:bodyPr',tx,wrap='none',lIns=0,rIns=0,tIns=0,bIns=0);el('a:noAutofit',bp);el('a:lstStyle',tx)
 p=el('a:p',tx);pp=el('a:pPr',p);el('a:buNone',pp)
 r=el('a:r',p);rp=el('a:rPr',r,lang='ja-JP',sz=round(size*100),dirty=0);fill=el('a:solidFill',rp);el('a:srgbClr',fill,val=color.lstrip('#'))
 el('a:latin',rp,typeface='Noto Sans JP Light' if font=='Light' else 'Noto Sans JP');el('a:ea',rp,typeface='Noto Sans JP Light' if font=='Light' else 'Noto Sans JP');el('a:t',r).text=s
 return sp
# Embedded spreadsheets make chart data editable through PowerPoint's Edit Data.
def workbook(labels,series):
 S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
 wb=E.Element('{'+S+'}workbook',nsmap={None:S,'r':NS['r']});sheets=E.SubElement(wb,'{'+S+'}sheets');E.SubElement(sheets,'{'+S+'}sheet',name='Data',sheetId='1',attrib={'{'+NS['r']+'}id':'rId1'})
 ws=E.Element('{'+S+'}worksheet',nsmap={None:S});sd=E.SubElement(ws,'{'+S+'}sheetData')
 rows=[['x']+[s[0] for s in series]]+[[v]+[s[1][i] for s in series] for i,v in enumerate(labels)]
 for i,row in enumerate(rows,1):
  rr=E.SubElement(sd,'{'+S+'}row',r=str(i))
  for j,v in enumerate(row):
   if v is None:continue
   cell=E.SubElement(rr,'{'+S+'}c',r=f'{chr(65+j)}{i}')
   if isinstance(v,(int,float)):E.SubElement(cell,'{'+S+'}v').text=str(v)
   else:cell.set('t','inlineStr');E.SubElement(E.SubElement(cell,'{'+S+'}is'),'{'+S+'}t').text=str(v)
 ct=E.Element('{'+CT+'}Types',nsmap={None:CT})
 for ext,kind in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml')]:E.SubElement(ct,'{'+CT+'}Default',Extension=ext,ContentType=kind)
 for path,kind in [('/xl/workbook.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),('/xl/worksheets/sheet1.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')]:E.SubElement(ct,'{'+CT+'}Override',PartName=path,ContentType=kind)
 rr=E.Element('{'+REL+'}Relationships',nsmap={None:REL});relation(rr,'rId1','officeDocument','xl/workbook.xml')
 wr=E.Element('{'+REL+'}Relationships',nsmap={None:REL});relation(wr,'rId1','worksheet','worksheets/sheet1.xml')
 bio=io.BytesIO()
 with ZipFile(bio,'w',ZIP_DEFLATED) as z:
  for n,t in {'[Content_Types].xml':ct,'_rels/.rels':rr,'xl/workbook.xml':wb,'xl/_rels/workbook.xml.rels':wr,'xl/worksheets/sheet1.xml':ws}.items():z.writestr(n,xml(t))
 return bio.getvalue()
def rich(parent,size=12):
 tx=el('c:txPr',parent);el('a:bodyPr',tx);el('a:lstStyle',tx);p=el('a:p',tx);pp=el('a:pPr',p);rp=el('a:defRPr',pp,sz=size*100);el('a:latin',rp,typeface='Noto Sans JP');el('a:ea',rp,typeface='Noto Sans JP');el('a:endParaRPr',p,lang='ja-JP')
def chart_title(parent,label):
 t=el('c:title',parent);tx=el('c:tx',t);r=el('c:rich',tx);el('a:bodyPr',r);el('a:lstStyle',r);p=el('a:p',r);pp=el('a:pPr',p);el('a:defRPr',pp,sz=1200);run=el('a:r',p);el('a:rPr',run,lang='ja-JP');el('a:t',run).text=label;el('c:overlay',t,val=0)
chart_count=0
def chart(tree,rels,sid,labels,series,x,y,w,h,kind='line',ylabel='',xlabel='',title=None,datalabel=False):
 global chart_count
 textbox(tree,sid+100,ylabel,x+22,y-24,w-44,22,12)
 if xlabel:textbox(tree,sid+101,xlabel,x+w/2-55,y+h-15,180,22,12)
 h-=27
 chart_count+=1;n=chart_count;rid='rId2'
 relation(rels,rid,'chart',f'../charts/chart{n}.xml')
 gf=el('p:graphicFrame',tree);nv=el('p:nvGraphicFramePr',gf);el('p:cNvPr',nv,id=sid,name=f'Editable chart {n}');el('p:cNvGraphicFramePr',nv);el('p:nvPr',nv);transform(gf,x,y,w,h,'p')
 gd=el('a:graphicData',el('a:graphic',gf),uri=NS['c']);el('c:chart',gd,**{'{'+NS['r']+'}id':rid})
 cs=E.Element('{'+NS['c']+'}chartSpace',nsmap={'c':NS['c'],'a':NS['a'],'r':NS['r']});el('c:lang',cs,val='ja-JP');ch=el('c:chart',cs)
 if title:chart_title(ch,title)
 else:el('c:autoTitleDeleted',ch,val=1)
 plot=el('c:plotArea',ch);el('c:layout',plot)
 tag={'bar':'barChart','line':'lineChart','scatter':'scatterChart'}[kind];ct=el('c:'+tag,plot)
 if kind=='bar':el('c:barDir',ct,val='col');el('c:grouping',ct,val='clustered')
 elif kind=='line':el('c:grouping',ct,val='standard')
 else:el('c:scatterStyle',ct,val='line')
 def ref(parent,tag,vals,col,numeric):
  q=el('c:'+tag,parent);nr=el('c:'+('numRef' if numeric else 'strRef'),q);el('c:f',nr).text=f"Data!${col}$2:${col}${len(vals)+1}";cache=el('c:'+('numCache' if numeric else 'strCache'),nr)
  if numeric:el('c:formatCode',cache).text='General'
  el('c:ptCount',cache,val=len(vals))
  for i,v in enumerate(vals):
   if v is not None:el('c:v',el('c:pt',cache,idx=i)).text=str(v)
 for i,(name,vals) in enumerate(series):
  ser=el('c:ser',ct);el('c:idx',ser,val=i);el('c:order',ser,val=i);tx=el('c:tx',ser);el('c:v',tx).text=name
  sp=el('c:spPr',ser);clr=['256B90','D97623','409267'][i%3]
  if kind=='bar':el('a:srgbClr',el('a:solidFill',sp),val=clr)
  else:
   ln=el('a:ln',sp,w=19050);el('a:srgbClr',el('a:solidFill',ln),val=clr);mk=el('c:marker',ser);el('c:symbol',mk,val='none')
  ref(ser,'xVal' if kind=='scatter' else 'cat',labels,'A',kind=='scatter')
  ref(ser,'yVal' if kind=='scatter' else 'val',vals,chr(66+i),True)
  if name=='証明時間中央値':
   eb=el('c:errBars');ser.insert(list(ser).index(ser.find('c:cat',NS)),eb)
   el('c:errDir',eb,val='y');el('c:errBarType',eb,val='both');el('c:errValType',eb,val='cust');el('c:noEndCap',eb,val=0)
   for side in ['plus','minus']:
    lit=el('c:numLit',el('c:'+side,eb));el('c:formatCode',lit).text='General';el('c:ptCount',lit,val=6)
    for j,r in enumerate(proof):
     if r['proof_status']=='verified':
      value=r['prove_seconds_max']-r['prove_seconds_median'] if side=='plus' else r['prove_seconds_median']-r['prove_seconds_min']
      el('c:v',el('c:pt',lit,idx=j)).text=str(value)
  if kind!='bar':el('c:smooth',ser,val=0)
 if datalabel:
  dl=el('c:dLbls',ct);el('c:numFmt',dl,formatCode='0.00',sourceLinked=0);el('c:dLblPos',dl,val='outEnd' if kind=='bar' else 't');el('c:showVal',dl,val=1)
 if kind=='bar':el('c:gapWidth',ct,val=80)
 el('c:axId',ct,val=10);el('c:axId',ct,val=20)
 for axis,pos,id,cross,label in [('valAx' if kind=='scatter' else 'catAx','b',10,20,xlabel),('valAx','l',20,10,ylabel)]:
  ax=el('c:'+axis,plot);el('c:axId',ax,val=id);sc=el('c:scaling',ax);el('c:orientation',sc,val='minMax');el('c:delete',ax,val=0);el('c:axPos',ax,val=pos)
  if pos=='l':el('c:majorGridlines',ax)
  if pos=='l':
   el('c:max',sc,val=13 if ylabel.startswith('LS参照') else (22 if ylabel.startswith('証明') else 4.2));el('c:min',sc,val=0)
  el('c:numFmt',ax,formatCode='General',sourceLinked=0);el('c:majorTickMark',ax,val='none');el('c:minorTickMark',ax,val='none');el('c:tickLblPos',ax,val='nextTo');rich(ax,10);el('c:crossAx',ax,val=cross);el('c:crosses',ax,val='autoZero')
  if axis=='catAx':el('c:auto',ax,val=1);el('c:lblAlgn',ax,val='ctr');el('c:lblOffset',ax,val=100)
  else:
   el('c:crossBetween',ax,val='between')
   if pos=='l':el('c:majorUnit',ax,val=2 if ylabel.startswith('LS参照') else (5 if ylabel.startswith('証明') else 1))
 if len(series)>1:
  leg=el('c:legend',ch);el('c:legendPos',leg,val='t');el('c:overlay',leg,val=0);rich(leg,10)
 el('c:plotVisOnly',ch,val=1);el('c:dispBlanksAs',ch,val='gap');rich(cs,12);ed=el('c:externalData',cs,**{'{'+NS['r']+'}id':'rId1'});el('c:autoUpdate',ed,val=0)
 parts[f'ppt/charts/chart{n}.xml']=xml(cs);content(f'ppt/charts/chart{n}.xml','application/vnd.openxmlformats-officedocument.drawingml.chart+xml')
 cr=E.Element('{'+REL+'}Relationships',nsmap={None:REL});relation(cr,'rId1','package',f'../embeddings/data{n}.xlsx');parts[f'ppt/charts/_rels/chart{n}.xml.rels']=xml(cr);parts[f'ppt/embeddings/data{n}.xlsx']=workbook(labels,series)
 content(f'ppt/embeddings/data{n}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def load(p):return json.loads((BASE/p).read_text())
ls=load('lomb/accuracy_summary.json');proof=load('lomb/proof_summary.json');vmd=load('diagnostics/vmd/trace.json');lsd=load('diagnostics/lomb/decoded_public.json')['data'];sc=int(lsd['selectedSubcarrier'])
shape_count=0
for num,items in enumerate(capture.pages,1):
 sld=E.Element('{'+NS['p']+'}sld',nsmap={k:NS[k] for k in ['a','r','p']},showMasterSp='0');tree=el('p:spTree',el('p:cSld',sld,name=f'Progress {num}'));nv=el('p:nvGrpSpPr',tree);el('p:cNvPr',nv,id=1,name='');el('p:cNvGrpSpPr',nv);el('p:nvPr',nv);el('p:grpSpPr',tree)
 rels=E.Element('{'+REL+'}Relationships',nsmap={None:REL});relation(rels,'rId1','slideLayout','../slideLayouts/slideLayout1.xml' if num==1 else '../slideLayouts/slideLayout2.xml');sid=2
 for item in items:
  sid+=1
  if item['kind']=='text':
   t=item;textbox(tree,sid,t['text'].replace('3回の中央値と範囲','3回の中央値'),t['x'],t['y']-t['size']*1.12,700-t['x'],t['size']*1.65,t['size'],t['font'],t['color']);continue
  p=Path(item['path']);x,y,w,h=[item[k] for k in ['x','y','w','h']]
  if p.stem=='vmd_centers':
   chart(tree,rels,sid,['K3 / R4 既定','K3 / R32 既定','K4 / R4','K3 / R4 中心変更'],[('LSとの差',[10.6565625,11.145,1.108125,1.108125])],x,y,w,h,'bar','LS参照との差 (BPM)',datalabel=True);continue
  if p.stem=='ls_difference':
   chart(tree,rels,sid,[str(r['subcarriers']) for r in ls],[('全tone参照との差',[r['absolute_difference_all_sc_bpm_mean'] for r in ls])],x,y,w,h,'line','全tone参照との差 (BPM)','サブキャリア本数',datalabel=True);continue
  if p.stem=='ls_proof':
   chart(tree,rels,sid,[str(r['subcarriers']) for r in proof],[('証明時間中央値',[r.get('prove_seconds_median') for r in proof])],x,y,w,h,'bar','証明生成時間 (秒)','サブキャリア本数',datalabel=True);continue
  # Keep scientific multi-panel plots and the code screenshot as replaceable images.
  rid='rId2';media=f'image{num*100+sid}.jpg';buf=io.BytesIO();Image.open(p).convert('RGB').save(buf,format='JPEG',quality=96);parts['ppt/media/'+media]=buf.getvalue();relation(rels,rid,'image','../media/'+media)
  pic=el('p:pic',tree);nv=el('p:nvPicPr',pic);el('p:cNvPr',nv,id=sid,name=p.stem,descr='Scientific plot / source: '+str(p.relative_to(ROOT)));el('p:cNvPicPr',nv);el('p:nvPr',nv)
  blip=el('p:blipFill',pic);el('a:blip',blip,**{'{'+NS['r']+'}embed':rid});el('a:fillRect',el('a:stretch',blip));pr=el('p:spPr',pic);transform(pr,x,y,w,h);el('a:avLst',el('a:prstGeom',pr,prst='rect'))

 for nv in tree.findall('.//p:cNvPr',NS): nv.set('id',str(num*1000+int(nv.get('id'))))
 el('a:masterClrMapping',el('p:clrMapOvr',sld));parts[f'ppt/slides/slide{num}.xml']=xml(sld);parts[f'ppt/slides/_rels/slide{num}.xml.rels']=xml(rels);content(f'ppt/slides/slide{num}.xml','application/vnd.openxmlformats-officedocument.presentationml.slide+xml');shape_count+=sid-2
pres=E.fromstring(parts['ppt/presentation.xml']);ids=pres.find('p:sldIdLst',NS);ids.clear()
rels=E.fromstring(parts['ppt/_rels/presentation.xml.rels'])
for r in list(rels):
 if r.get('Type').endswith('/slide'):rels.remove(r)
for i in range(1,11):
 rid=f'rBriefSlide{i}';el('p:sldId',ids,id=1000+i,**{'{'+NS['r']+'}id':rid});relation(rels,rid,'slide',f'slides/slide{i}.xml')
parts['ppt/presentation.xml']=xml(pres);parts['ppt/_rels/presentation.xml.rels']=xml(rels);parts['[Content_Types].xml']=xml(cts)
# Preserve original master/theme parts byte-for-byte, remove stale authoring metadata thumbnail.
parts.pop('docProps/thumbnail.jpeg',None)
for f in ['docProps/app.xml','docProps/core.xml']:
 if f in parts:
  t=E.fromstring(parts[f])
  for e in t.iter():
   if E.QName(e).localname=='Slides':e.text='10'
   if E.QName(e).localname=='title':e.text='2026年10月26日 進捗報告'
  parts[f]=xml(t)
# Remove orphan thumbnail relationship.
rr=E.fromstring(parts['_rels/.rels'])
for r in list(rr):
 if r.get('Type','').endswith('/thumbnail'):rr.remove(r)
parts['_rels/.rels']=xml(rr)
OUT.parent.mkdir(exist_ok=True,parents=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
 for n,data in parts.items():z.writestr(n,data)
(HERE/'validation.json').write_text(json.dumps({'slides':10,'native_editable_charts':chart_count,'text_and_image_shapes':shape_count,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'theme_and_layouts_preserved':True,'native_app_visual_check':False},indent=2)+'\n')
print(OUT)
