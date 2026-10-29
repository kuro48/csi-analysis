#!/usr/bin/env python3
"""Check that the final report has complete real-data evidence and live links."""
import csv
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]

    def handle_starttag(self,tag,attrs):
        for name,value in attrs:
            if name in ('src','href'):
                self.links.append(value)


proof=json.loads((BASE/'lomb/proof_summary.json').read_text())
assert sorted(r['subcarriers'] for r in proof)==[1,2,4,8,16,32]
verified = [r for r in proof if r['proof_status']=='verified']
assert sorted(r['subcarriers'] for r in verified)==[1,2,4,8,16]
assert all(len(r['measurements'])==3 and all(m['verified'] for m in r['measurements']) for r in verified)
limited = [r for r in proof if r['subcarriers']==32][0]
assert limited['proof_status']=='setup_timeout' and limited.get('prove_seconds_median') is None
attempts=json.loads((BASE/'lomb/failures/attempts.json').read_text())
assert any(a['status']=='failed_heap_out_of_memory' and a['node_max_old_space_mb']==8192 for a in attempts)
assert any(a['status']=='setup_timeout' and a['configured_timeout_seconds']==1800
           and a['node_max_old_space_mb']==12288 for a in attempts)
for a in attempts:
    assert (BASE/'lomb/failures'/a['log']).exists()
with (BASE/'lomb/accuracy.csv').open() as f:
    rows=list(csv.DictReader(f))
assert len(rows)==48 and len({r['window_id'] for r in rows})==8
assert all(r['data_kind']=='real_csi' and r['status']=='ok'
           and r['witness_reference_match']=='True' for r in rows)
vmd=json.loads((BASE/'vmd/all_windows_circuit_validation.json').read_text())
assert len(vmd)==32 and all(r['all_final_spectra_and_centers_match'] for r in vmd)
vp=json.loads((BASE/'diagnostics/vmd/proof_validation.json').read_text())
lp=json.loads((BASE/'diagnostics/lomb/proof_metrics.json').read_text())
assert vp['proof_verified'] and vp['proof_public_matches_display'] and vp['tampered_public_rejected']
assert lp['verified'] and lp['proof_public_equals_decoded_public'] and lp['tampered_intermediate_public_value_rejected']
assert json.loads((BASE/'diagnostics/vmd/public.json').read_text()) == json.loads((BASE/'diagnostics/vmd/proof_public.json').read_text())
assert json.loads((BASE/'diagnostics/lomb/public_from_witness.json').read_text()) == json.loads((BASE/'diagnostics/lomb/public.json').read_text())
assert all(r['rendered'] for r in json.loads((HERE/'trace_render_validation.json').read_text()))
for name in ['report.html','report_details.html','summary.html','trace_viewer.html']:
    path=HERE/name
    text=path.read_text()
    assert '合成' not in text and 'MAE' not in text
    assert '測定中' not in text and '未測定' not in text
    parser=Links();parser.feed(text)
    for link in parser.links:
        if not link.startswith(('https:','http:','#')):
            assert (HERE/link).exists(),link
for path in HERE.glob('code_*.json'):
    source=json.loads(path.read_text())
    assert hashlib.sha256((ROOT/('zkp/experiments/'+source['source'][9:] if source['source'].startswith('research/') else source['source'])).read_bytes()).hexdigest()==source['source_sha256'],path
result={'status':'PASS','raw_recordings':8,'ls_actual_witness_cases':48,
        'vmd_actual_witness_cases':32,'ls_proof_configurations_completed':5,'ls_verified_proofs':15,
        'ls_32_sc_setup_status':'timeout_1800_seconds',
        'main_report_real_data_only':True,'code_excerpt_hashes_match':True,'local_links_exist':True,
        'diagnostic_proofs_verified':2,'diagnostic_public_values_match_display':True,
        'diagnostic_tampered_values_rejected':True,'viewer_bookmarked_views_rendered':2}
(HERE/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
