const { randomBytes } = require("crypto");

const FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;

// Input formatting only. Never compute scores or remove/reorder candidates.
function prepareInput(raw, capacity = 64) {
  if (!Number.isInteger(capacity) || capacity < 1 || capacity > 4096) throw Error("capacity must be 1..4096");
  const count = raw.csiI?.[0]?.length;
  if (!Number.isInteger(count) || count < 1 || count > capacity) {
    throw Error(`All ${count ?? 0} columns must fit capacity ${capacity}; compile a larger circuit, never subsample columns`);
  }
  for (const name of ["csiI", "csiQ"]) {
    if (!Array.isArray(raw[name]) || raw[name].length !== 64) throw Error(`${name} requires 64 samples`);
    for (const row of raw[name]) {
      if (!Array.isArray(row) || row.length !== count || row.some(x => !Number.isInteger(x) || x < 0 || x > 4095)) {
        throw Error(`${name} requires equally sized rows of encoded 12-bit integers`);
      }
    }
  }
  if (raw.candidateCount !== undefined && raw.candidateCount !== count) {
    throw Error("Supply unpadded columns; candidateCount must match their actual number");
  }
  const times = raw.timestampsMs;
  if (!Array.isArray(times) || times.length !== 64 || times[0] !== 0 || times.some(
    (x, i) => !Number.isInteger(x) || x < 0 || x >= 2 ** 24 || (i > 0 && x <= times[i - 1]),
  )) throw Error("timestampsMs requires 64 strictly increasing 24-bit integers starting at zero");
  if (raw.commitmentNonce !== undefined && (typeof raw.commitmentNonce !== "string" || !/^\d+$/.test(raw.commitmentNonce))) {
    throw Error("commitmentNonce must be a decimal string");
  }
  let nonce;
  if (raw.commitmentNonce !== undefined) nonce = BigInt(raw.commitmentNonce);
  else do { nonce = BigInt(`0x${randomBytes(32).toString("hex")}`); } while (nonce === 0n || nonce >= FIELD);
  if (nonce <= 0n || nonce >= FIELD) throw Error("commitmentNonce must be a nonzero canonical BN254 field element");
  return {
    csiI: raw.csiI.map(row => [...row, ...Array(capacity - count).fill(2048)]),
    csiQ: raw.csiQ.map(row => [...row, ...Array(capacity - count).fill(2048)]),
    timestampsMs: [...times], candidateCount: count, commitmentNonce: nonce.toString(),
  };
}

function syntheticInput() {
  const times = Array.from({ length: 64 }, (_, i) => Math.round((i * 0.94 + 0.035 * Math.sin(i * 0.73)) * 1000));
  return {
    csiI: times.map(t => Array.from({ length: 64 }, (_, sc) => 2048 + Math.round(
      sc === 13 ? 900 + 150 * Math.sin(2 * Math.PI * 0.25 * t / 1000) : 900,
    ))),
    csiQ: times.map(() => Array(64).fill(2048)), timestampsMs: times,
  };
}

module.exports = { prepareInput, syntheticInput };
