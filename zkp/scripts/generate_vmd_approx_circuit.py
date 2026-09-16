#!/usr/bin/env python3
import math
from pathlib import Path

N,B,K,R,S=128,63,3,4,1000
OUT=Path(__file__).resolve().parents[1]/'circuits/csi_vmd_approx.circom'
def tab(f):
    return ',\n'.join('['+', '.join(str(round(S*f(2*math.pi*(j+1)*t/N))) for t in range(N))+']' for j in range(B))
def main():
    x=['pragma circom 2.0.0;','include "circomlib/circuits/bitify.circom";','include "circomlib/circuits/comparators.circom";','template Div(){ signal input n; signal input d; signal output q; signal output r; signal s; signal a; s <-- n > 21888242871839275222246405745257275088548364400416034343698204186575808495617/2 ? 1:0; a <-- s ? -n:n; q <-- (s ? -a:a)/d; r <-- a-(s ? -q:q)*d; s*(s-1)===0; a===n; a===q*d+r; }','template V(){ signal input waveform[128]; signal output isNormal; signal output estimatedFrequencyBin; signal output selectedMode0based; var C[63][128]=[',tab(math.cos),']; var T[63][128]=[',tab(math.sin),']; signal fc[63]; signal fs[63];']
    x += ['for(var j=0;j<63;j++){var ac=0;var ai=0;for(var t=0;t<128;t++){ac+=C[j][t]*waveform[t];ai+=T[j][t]*waveform[t];}fc[j]<==ac;fs[j]<==ai;}','signal ur[4][3][63]; signal ui[4][3][63]; signal center[5][3]; center[0][0]<==8;center[0][1]<==24;center[0][2]<==48;']
    for r in range(R):
      for k in range(K):
       for j in range(B):
        others=[]
        for i in range(K):
         if i!=k: others.append(f'ur[{r}][{i}][{j}]' if i<k else (f'ur[{r-1}][{i}][{j}]' if r else '0'))
        den=f'(1+({j+1}-center[{r}][{k}])*({j+1}-center[{r}][{k}]))'
        x += [f'signal nr{r}_{k}_{j};nr{r}_{k}_{j}<==fc[{j}]-({"+".join(others)});component q{r}_{k}_{j}=Div();q{r}_{k}_{j}.n<==nr{r}_{k}_{j};q{r}_{k}_{j}.d<=={den};ur[{r}][{k}][{j}]<==q{r}_{k}_{j}.q;','signal ni'+f'{r}_{k}_{j};']
        # Imaginary update uses the same fixed denominator.
        x += [f'component z{r}_{k}_{j}=Div();z{r}_{k}_{j}.n<==fs[{j}];z{r}_{k}_{j}.d<=={den};ui[{r}][{k}][{j}]<==z{r}_{k}_{j}.q;']
       x += [f'center[{r+1}][{k}]<==center[{r}][{k}];']
    x += ['signal p[3][63]; signal pr[3][63]; signal pi[3][63]; for(var k=0;k<3;k++)for(var j=0;j<63;j++){ pr[k][j]<==ur[3][k][j]*ur[3][k][j]; pi[k][j]<==ui[3][k][j]*ui[3][k][j]; p[k][j]<==pr[k][j]+pi[k][j]; } selectedMode0based<==0;estimatedFrequencyBin<==0;isNormal<==0;}component main=V();']
    OUT.write_text('\n'.join(x)+'\n')
if __name__=='__main__':main()
