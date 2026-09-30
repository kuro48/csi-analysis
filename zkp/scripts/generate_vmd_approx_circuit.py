#!/usr/bin/env python3
"""Generate csi_vmd_approx.circom.

The circuit consumes N=128 signed integer samples in [-100,100], computes
positive DFT bins 1..63 with cos/sin constants scaled by 1000, then runs
K=3 modes for R=4 sequential VMD rounds (tau=0). Division is signed
truncation toward zero with bounded 48-bit magnitudes; energies and adaptive
center weighted sums are bounded to 103 and 109 bits respectively.
"""
import math
from pathlib import Path

N, B, K, R, S = 128, 63, 3, 4, 1000
OUT = Path(__file__).resolve().parents[1] / "circuits/csi_vmd_approx.circom"


def tab(f):
    return ",\n".join(
        "[" + ", ".join(str(round(S * f(2 * math.pi * (j + 1) * t / N))) for t in range(N)) + "]" for j in range(B)
    )


def main():
    x = [
        "pragma circom 2.0.0;",
        'include "circomlib/circuits/bitify.circom";',
        'include "circomlib/circuits/comparators.circom";',
        "template Div(){ signal input n; signal input d; signal output q; signal output r; signal s; signal a; signal qm; component ab=Num2Bits(48); component db=Num2Bits(16); component qb=Num2Bits(48); component rb=Num2Bits(16); component lt=LessThan(16); component dz=IsZero(); s <-- n < 0 ? 1:0; s*(s-1)===0; a <-- s ? -n:n; a === (1-2*s)*n; ab.in <== a; dz.in <== d; dz.out === 0; db.in <== d; qm <-- a \\ d; r <-- a % d; qb.in <== qm; rb.in <== r; lt.in[0] <== r; lt.in[1] <== d; lt.out === 1; a === qm*d+r; q <== (1-2*s)*qm; }",
        "template UnsignedDiv(){signal input n;signal input d;signal output q;signal output r;q <-- n \\ d;r <-- n % d;n===q*d+r;}",
        "template V(){ signal input waveform[128]; signal output isNormal; component wb[128]; component wr[128]; for(var wt=0;wt<128;wt++){ wb[wt]=Num2Bits(8); wb[wt].in <== waveform[wt]+100; wr[wt]=LessThan(8); wr[wt].in[0] <== waveform[wt]+100; wr[wt].in[1] <== 201; wr[wt].out === 1; } signal output estimatedFrequencyBin; signal output selectedMode0based; var C[63][128]=[",
        tab(math.cos),
        "]; var T[63][128]=[",
        tab(math.sin),
        "]; signal fc[63]; signal fs[63];",
    ]
    x += [
        "for(var j=0;j<63;j++){var ac=0;var ai=0;for(var t=0;t<128;t++){ac+=C[j][t]*waveform[t];ai+=T[j][t]*waveform[t];}fc[j]<==ac;fs[j]<==ai;}",
        "signal ur[4][3][63]; signal ui[4][3][63]; signal center[5][3]; center[0][0]<==8;center[0][1]<==24;center[0][2]<==48;",
    ]
    for r in range(R):
        for k in range(K):
            for j in range(B):
                others = []
                for i in range(K):
                    if i != k:
                        others.append(f"ur[{r}][{i}][{j}]" if i < k else (f"ur[{r-1}][{i}][{j}]" if r else "0"))
                den = f"(1+({j+1}-center[{r}][{k}])*({j+1}-center[{r}][{k}]))"
                x += [
                    f'signal nr{r}_{k}_{j};nr{r}_{k}_{j}<==fc[{j}]-({"+".join(others)});component q{r}_{k}_{j}=Div();q{r}_{k}_{j}.n<==nr{r}_{k}_{j};q{r}_{k}_{j}.d<=={den};ur[{r}][{k}][{j}]<==q{r}_{k}_{j}.q;',
                    "",
                ]
                # Imaginary update uses the same fixed denominator.

                othersi = []
                for i in range(K):
                    if i != k:
                        othersi.append(f"ui[{r}][{i}][{j}]" if i < k else (f"ui[{r-1}][{i}][{j}]" if r else "0"))
                x += [
                    f'signal ni{r}_{k}_{j};ni{r}_{k}_{j}<==fs[{j}]-({"+".join(othersi)});component z{r}_{k}_{j}=Div();z{r}_{k}_{j}.n<==ni{r}_{k}_{j};z{r}_{k}_{j}.d<=={den};ui[{r}][{k}][{j}]<==z{r}_{k}_{j}.q;'
                ]
            # Adaptive center: weighted energy mean, retaining old center on zero energy.
            qn = f"cq{r}_{k}"
            rn = f"cr{r}_{k}"
            tn = f"te{r}_{k}"
            wn = f"we{r}_{k}"
            bits = f"component bq{r}_{k}=Num2Bits(6);component br{r}_{k}=Num2Bits(112);component bt{r}_{k}=Num2Bits(112);component bz{r}_{k}=IsZero();component bl{r}_{k}=LessThan(112);"
            es = " ".join(
                f"signal e{r}_{k}_{j};signal er{r}_{k}_{j};signal ei{r}_{k}_{j};er{r}_{k}_{j}<==ur[{r}][{k}][{j}]*ur[{r}][{k}][{j}];ei{r}_{k}_{j}<==ui[{r}][{k}][{j}]*ui[{r}][{k}][{j}];e{r}_{k}_{j}<==er{r}_{k}_{j}+ei{r}_{k}_{j};"
                for j in range(B)
            )
            sums = f"signal {tn};signal {wn};{tn}<=={' + '.join(f'e{r}_{k}_{j}' for j in range(B))};{wn}<=={' + '.join(f'{j+1}*e{r}_{k}_{j}' for j in range(B))};"
            div = f"{bits}component bd{r}_{k}=UnsignedDiv();bd{r}_{k}.n<=={wn};bd{r}_{k}.d<=={tn}+bz{r}_{k}.out;{qn}<==bd{r}_{k}.q;{rn}<==bd{r}_{k}.r;"
            x += [
                f"signal {qn};signal {rn};"
                + bits
                + es
                + sums
                + f"bz{r}_{k}.in<=={tn};component bd{r}_{k}=UnsignedDiv();bd{r}_{k}.n<=={wn};bd{r}_{k}.d<=={tn}+bz{r}_{k}.out;{qn}<==bd{r}_{k}.q;{rn}<==bd{r}_{k}.r;bq{r}_{k}.in<=={qn};{wn}==={qn}*({tn}+bz{r}_{k}.out)+{rn};br{r}_{k}.in<=={rn};bt{r}_{k}.in<=={tn}+bz{r}_{k}.out;bl{r}_{k}.in[0]<=={rn};bl{r}_{k}.in[1]<=={tn}+bz{r}_{k}.out;bl{r}_{k}.out===1;center[{r+1}][{k}]<=={qn}+bz{r}_{k}.out*center[{r}][{k}];component bc{r}_{k}=Num2Bits(6);bc{r}_{k}.in<==center[{r+1}][{k}];"
            ]
    x += [
        "signal p[3][63]; signal pr[3][63]; signal pi[3][63]; for(var k=0;k<3;k++)for(var j=0;j<63;j++){ pr[k][j]<==ur[3][k][j]*ur[3][k][j]; pi[k][j]<==ui[3][k][j]*ui[3][k][j]; p[k][j]<==pr[k][j]+pi[k][j]; } signal bp[189]; signal bm[189]; signal bb[189]; component g[189]; bp[0]<==p[0][0];bm[0]<==0;bb[0]<==1; for(var h=1;h<189;h++){var kk=h \\ 63;var jj=h%63;g[h]=GreaterThan(100);g[h].in[0]<==p[kk][jj];g[h].in[1]<==bp[h-1];bp[h]<==bp[h-1]+g[h].out*(p[kk][jj]-bp[h-1]);bm[h]<==bm[h-1]+g[h].out*(kk-bm[h-1]);bb[h]<==bb[h-1]+g[h].out*((jj+1)-bb[h-1]);} component zz=IsZero();zz.in<==bp[188]; component ge=GreaterEqThan(6);component le=LessEqThan(6);ge.in[0]<==bb[188];ge.in[1]<==7;le.in[0]<==bb[188];le.in[1]<==23;signal ib;ib<==ge.out*le.out;estimatedFrequencyBin<==(1-zz.out)*bb[188];selectedMode0based<==(1-zz.out)*bm[188];isNormal<==ib*(1-zz.out);}component main=V();"
    ]
    text = "// Generated by scripts/generate_vmd_approx_circuit.py. Do not edit.\n" + "\n".join(x)
    OUT.write_text(text.replace(";", ";\n").rstrip() + "\n")


if __name__ == "__main__":
    main()
