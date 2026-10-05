#!/usr/bin/env node

/* Canonical Poseidon chain used by the Python/Circom hybrid pipeline. */
const fs = require("fs");
const { buildPoseidon } = require("circomlibjs");

async function main() {
  const request = JSON.parse(fs.readFileSync(0, "utf8"));
  const poseidon = await buildPoseidon();
  const F = poseidon.F;
  const domainTag = BigInt(request.domainTag);
  const nonce = BigInt(request.nonce);
  const version = BigInt(request.version);
  const metadata = (request.metadata || []).map(BigInt);
  const values = (request.values || []).map(BigInt);

  let state = poseidon([domainTag, nonce, version]);
  for (const value of [...metadata, ...values]) {
    state = poseidon([state, value]);
  }

  process.stdout.write(JSON.stringify({ commitment: F.toObject(state).toString() }));
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exit(1);
});
