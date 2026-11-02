import { sepoliaEnvironment } from './networks.mjs';

Object.assign(process.env, sepoliaEnvironment(process.env));
await import('./deploy.mjs');
