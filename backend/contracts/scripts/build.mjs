import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import solc from 'solc';
import { id } from 'ethers';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export function compile(sources) {
  const output = JSON.parse(solc.compile(JSON.stringify({ language: 'Solidity', sources,
    settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'paris',
      outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object', 'evm.deployedBytecode.object'] } } } })));
  const errors = (output.errors ?? []).filter(e => e.severity === 'error');
  if (errors.length) throw new Error(errors.map(e => e.formattedMessage).join('\n'));
  return output.contracts;
}
export function build(names = ['csi_breathing_certificate']) {
  mkdirSync(resolve(root, 'build/onchain'), { recursive: true });
  const circuits = names.map(name => {
    if (!/^csi_[a-z0-9_]+$/.test(name)) throw new Error('Invalid circuit name');
    const zkey = resolve(root, '../../zkp/keys', `${name}_final.zkey`);
    const verifierPath = resolve(root, 'build/onchain', `${name}.sol`);
    const vkeyPath = resolve(root, 'build/onchain', `${name}.vkey.json`);
    const cli = resolve(root, 'node_modules/snarkjs/build/cli.cjs');
    execFileSync(process.execPath, [cli, 'zkey', 'export', 'solidityverifier', zkey, verifierPath]);
    execFileSync(process.execPath, [cli, 'zkey', 'export', 'verificationkey', zkey, vkeyPath]);
    const vkey = readFileSync(vkeyPath);
    const publicSignalCount = JSON.parse(vkey).nPublic;
    if (publicSignalCount < 1 || publicSignalCount > 256) throw new Error('Unsupported public input count');
    const verificationKeyHash = '0x' + createHash('sha256').update(vkey).digest('hex');
    const artifact = compile({ 'Verifier.sol': { content: readFileSync(verifierPath, 'utf8') } })['Verifier.sol'].Groth16Verifier;
    return { name, circuitId: id(`${name}:${verificationKeyHash}`), verificationKeyHash, publicSignalCount,
      selector: id(`verifyProof(uint256[2],uint256[2][2],uint256[2],uint256[${publicSignalCount}])`).slice(0, 10),
      abi: artifact.abi, bytecode: '0x' + artifact.evm.bytecode.object };
  });
  const artifact = compile({ 'Registry.sol': { content: readFileSync(resolve(root, 'VerifiedProofRegistry.sol'), 'utf8') } })['Registry.sol'].VerifiedProofRegistry;
  const build = { compiler: solc.version(), circuits, registry: { abi: artifact.abi, bytecode: '0x' + artifact.evm.bytecode.object } };
  writeFileSync(resolve(root, 'build/onchain/compiled.json'), JSON.stringify(build, null, 2));
  return build;
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = build(process.argv.slice(2).length ? process.argv.slice(2) : undefined);
  console.log(`Built registry + ${result.circuits.length} verifier(s) from existing proving keys.`);
}
