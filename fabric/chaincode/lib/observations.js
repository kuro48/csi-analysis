'use strict';
const { Contract } = require('fabric-contract-api');
const { createHash, X509Certificate } = require('node:crypto');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { groth16 } = require('snarkjs');
const { normalize, proofDigest, protocol } = require('./proof');
const hash = data => createHash('sha256').update(data).digest('hex');

function reader(ctx, config) {
  if (ctx.stub.getChannelID() !== config.channelName || !config.readerMspIds.includes(ctx.clientIdentity.getMSPID())) throw new Error('Unauthorized reader');
}
function metadata(item, config) {
  return { status: 'recorded', observationId: item.observationId, patientRef: item.patientRef,
    observedAt: item.observedAt, durationSeconds: item.durationSeconds, proofDigest: item.proofDigest,
    payloadHash: item.payloadHash, transactionId: item.transactionId, deploymentId: config.deploymentId };
}

class Observations extends Contract {
  constructor(config, vkeyBytes) {
    super('Observations');
    this.config = config || JSON.parse(readFileSync(join(__dirname, '../deployment/config.json')));
    const bytes = vkeyBytes || readFileSync(join(__dirname, '../deployment', this.config.verificationKeyFile || 'csi_breathing_certificate.vkey.json'));
    if (hash(bytes) !== this.config.verificationKeyHash.replace(/^0x/, '')) throw new Error('Verification key mismatch');
    this.vkey = JSON.parse(bytes);
    if (this.vkey.nPublic !== protocol(this.config).count || this.vkey.protocol !== 'groth16' || this.vkey.curve !== 'bn128') throw new Error('Unsupported verification key');
  }

  async GetConfiguration(ctx) {
    reader(ctx, this.config);
    return JSON.stringify(this.config);
  }

  async RecordObservation(ctx, encoded) {
    reader(ctx, this.config);
    const certificateHash = hash(new X509Certificate(ctx.clientIdentity.getIDBytes()).raw);
    if (ctx.clientIdentity.getMSPID() !== this.config.recorderMspId || certificateHash !== this.config.recorderCertificateHash) throw new Error('Unauthorized recorder');
    if (Buffer.byteLength(encoded) > 16384) throw new Error('Observation too large');
    const input = normalize(JSON.parse(encoded), this.config);
    if (input.observedAt + input.durationSeconds > Number(ctx.stub.getTxTimestamp().seconds.toString()) + 300) throw new Error('Future observation');
    const key = ctx.stub.createCompositeKey('observation', [input.observationId]);
    const payloadHash = hash(JSON.stringify(input));
    const existing = await ctx.stub.getState(key);
    if (existing.length) {
      const item = JSON.parse(existing.toString());
      if (item.payloadHash !== payloadHash) throw new Error('Conflicting observation ID');
      return JSON.stringify({...metadata(item, this.config), reused: true});
    }
    const digest = proofDigest(input);
    const replayKey = ctx.stub.createCompositeKey('proof', [digest]);
    if ((await ctx.stub.getState(replayKey)).length) throw new Error('Duplicate proof');
    // As with EVM: store first. No verified flag or isNormal result at recording time.
    const item = {...input, proofDigest: digest, payloadHash, transactionId: ctx.stub.getTxID()};
    await ctx.stub.putState(key, Buffer.from(JSON.stringify(item)));
    await ctx.stub.putState(replayKey, Buffer.from(input.observationId));
    ctx.stub.setEvent('ObservationRecorded', Buffer.from(JSON.stringify({observationId: input.observationId, patientRef: input.patientRef, observedAt: input.observedAt})));
    return JSON.stringify({...metadata(item, this.config), reused: false});
  }

  async ReadObservation(ctx, observationId) {
    reader(ctx, this.config);
    if (!/^0x[0-9a-f]{64}$/.test(observationId)) throw new Error('Invalid identifier');
    const data = await ctx.stub.getState(ctx.stub.createCompositeKey('observation', [observationId]));
    return JSON.stringify(data.length ? metadata(JSON.parse(data.toString()), this.config) : {status:'not_found'});
  }

  async VerifyObservation(ctx, observationId) {
    reader(ctx, this.config);
    if (!/^0x[0-9a-f]{64}$/.test(observationId)) throw new Error('Invalid identifier');
    const data = await ctx.stub.getState(ctx.stub.createCompositeKey('observation', [observationId]));
    if (!data.length) throw new Error('Observation not found');
    const item = JSON.parse(data.toString());
    // Groth16 pairing verification runs INSIDE the endorsing peer's chaincode.
    if (await groth16.verify(this.vkey, item.publicSignals, item.proof) !== true) throw new Error('Invalid proof');
    return JSON.stringify({...metadata(item, this.config), status:'verified', isNormal:item.publicSignals[protocol(this.config).index] === '1', debugInput:this.config.debugMode});
  }
}
module.exports = Observations;
