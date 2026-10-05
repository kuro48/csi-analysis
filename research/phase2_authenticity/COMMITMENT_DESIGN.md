# Hybrid ZKP commitment format

Status: implemented format version `1`.

The hybrid pipeline uses commitments only at semantic stage boundaries. It does
not hash every temporary FFT or PCA array.

## Canonical Poseidon chain

```text
state_0 = Poseidon(domain_tag, nonce, format_version)
state_i = Poseidon(state_(i-1), item_i)
commitment = state_last
```

`item_i` is the metadata sequence followed by the data sequence. All dimensions
are fixed by metadata, and matrices are flattened sample-major then
subcarrier-major. Complex CSI stores interleaved `I, Q` values.

| Boundary | Domain tag | Metadata | Value encoding |
|---|---:|---|---|
| C0 raw CSI | `0x43534900` | rows, columns, scale=1000, offset=2^31 | `rint(component*scale)+2^31`, I then Q |
| C1 VMD input | `0x43534901` | length, offset=2^10 | signed integer + 2^10 |

The nonce is a non-zero random 128-bit integer. The commitment is binding to
the nonce but the nonce stays private in the proof. Domain separation prevents
the same integer list being interpreted as two different pipeline artifacts.

## Reference implementation

Python calls the same `circomlibjs` Poseidon implementation used by Circom's
`circomlib` constants:

```python
nonce = new_commitment_nonce()
c1 = commit_vmd_input(certificate_input["vmdInput"], nonce)
print(c1.value)
```

```javascript
let state = poseidon([domainTag, nonce, version]);
for (const value of [...metadata, ...values]) {
  state = poseidon([state, value]);
}
```

## Security boundary

C0/C1 prove that later stages use the committed values. A hash alone does not
prove that Python executed FFT, PCA, or VMD correctly. That transition requires
a relation-checking circuit or an independently trusted device signature.
