"""Generate isolated circuit variants using the production generator as source."""
import argparse
from pathlib import Path
from model import INITIAL_CENTERS

ROOT = Path(__file__).resolve().parents[3]


def generate(k, r, output, initial_centers=None):
    if not 1 <= k <= 8 or r < 1:
        raise ValueError("K must be 1..8 and R positive")
    centers = INITIAL_CENTERS[:k] if initial_centers is None else initial_centers
    if len(centers) != k or any(not 1 <= c <= 63 for c in centers):
        raise ValueError("one initial center in 1..63 for each mode required")
    src = (ROOT / 'zkp/scripts/generate_vmd_approx_circuit.py').read_text()
    src = src.replace('N, B, K, R, S = 128, 63, 3, 4, 1000', f'N, B, K, R, S = 128, 63, {k}, {r}, 1000')
    src = src.replace('OUT = Path(__file__).resolve().parents[1] / "circuits/csi_vmd_approx.circom"', f'OUT = Path({str(output)!r})')
    src = src.replace('signal ur[4][3][63]; signal ui[4][3][63]; signal center[5][3]; center[0][0]<==8;center[0][1]<==24;center[0][2]<==48;',
        f'signal ur[{r}][{k}][63]; signal ui[{r}][{k}][63]; signal center[{r+1}][{k}];' + ''.join(f'center[0][{i}]<=={c};' for i,c in enumerate(centers)))
    # Only replace the final selection literal; other bounds must remain unchanged.
    start = src.index('"signal p[3][63];')
    end = src.index('\n    ]', start)
    selection = src[start:end]
    for old,new in [('p[3][63]',f'p[{k}][63]'),('pr[3][63]',f'pr[{k}][63]'),('pi[3][63]',f'pi[{k}][63]'),('k<3',f'k<{k}'),('ur[3]',f'ur[{r-1}]'),('ui[3]',f'ui[{r-1}]'),('[189]',f'[{63*k}]'),('h<189',f'h<{63*k}'),('[188]',f'[{63*k-1}]')]:
        selection = selection.replace(old,new)
    src = src[:start] + selection + src[end:]
    src = src.replace('{"+".join(others)}', '{"+".join(others) or "0"}').replace('{"+".join(othersi)}', '{"+".join(othersi) or "0"}')
    namespace = {'__name__': 'variant_generator', '__file__': str(ROOT / 'zkp/scripts/generate_vmd_approx_circuit.py')}
    exec(compile(src, '<parameterized production generator>', 'exec'), namespace)
    namespace['main']()
    return output

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--modes',type=int,required=True);p.add_argument('--iterations',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();generate(a.modes,a.iterations,a.output)
