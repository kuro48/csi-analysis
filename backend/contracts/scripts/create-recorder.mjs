import { mkdirSync, readFileSync, writeFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { Wallet } from 'ethers';

const path = resolve(process.argv[2] || '../../.local/observations/recorder.key');
mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
try { writeFileSync(path, Wallet.createRandom().privateKey, { flag: 'wx', mode: 0o600 }); }
catch (error) { if (error.code !== 'EEXIST') throw error; }
if (statSync(path).mode & 0o077) throw new Error('Key file must have mode 0600');
// Only the public address is printed, never the private key.
console.log(new Wallet(readFileSync(path, 'utf8').trim()).address);
