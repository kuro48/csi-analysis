import grpc from "@grpc/grpc-js";
import { connect, hash, signers } from "@hyperledger/fabric-gateway";
import { createPrivateKey } from "node:crypto";
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { normalize, proofDigest } = require("./chaincode/lib/proof.js");

export function openGateway(config, role) {
  const identity = config[role];
  if (!identity || !["reader", "writer"].includes(role))
    throw new Error("Missing gateway identity");
  const client = new grpc.Client(
    config.peerEndpoint,
    grpc.credentials.createSsl(readFileSync(config.tlsRootCert)),
    {
      "grpc.ssl_target_name_override": config.peerHostAlias,
      "grpc.default_authority": config.peerHostAlias,
    },
  );
  const gateway = connect({
    client,
    identity: {
      mspId: identity.mspId,
      credentials: readFileSync(identity.certificate),
    },
    signer: signers.newPrivateKeySigner(
      createPrivateKey(readFileSync(identity.privateKey)),
    ),
    hash: hash.sha256,
    evaluateOptions: () => ({ deadline: Date.now() + 30000 }),
    endorseOptions: () => ({ deadline: Date.now() + 60000 }),
    submitOptions: () => ({ deadline: Date.now() + 30000 }),
    commitStatusOptions: () => ({ deadline: Date.now() + 120000 }),
  });
  const contract = gateway
    .getNetwork(config.channelName)
    .getContract(config.chaincodeName, "Observations");
  const decode = (bytes) => JSON.parse(Buffer.from(bytes).toString("utf8"));
  async function configuration() {
    const actual = decode(
      await contract.evaluateTransaction("GetConfiguration"),
    );
    if (actual.deploymentId !== config.deploymentId)
      throw new Error("Fabric deployment mismatch");
    return actual;
  }
  return {
    config,
    role,
    contract,
    configuration,
    async metadata(id) {
      return decode(await contract.evaluateTransaction("ReadObservation", id));
    },
    async record(payload) {
      if (role !== "writer")
        throw new Error("Reader identity cannot submit observations");
      const input = normalize(payload, config);
      const started = performance.now();
      const proposal = contract.newProposal("RecordObservation", {
        arguments: [JSON.stringify(input)],
      });
      const transaction = await proposal.endorse();
      const endorsed = performance.now();
      const commit = await transaction.submit();
      const submitted = performance.now();
      const status = await commit.getStatus();
      const finished = performance.now();
      if (!status.successful)
        throw new Error(`Fabric commit invalid: ${status.code}`);
      const result = decode(transaction.getResult());
      if (
        result.deploymentId !== config.deploymentId ||
        result.observationId !== input.observationId ||
        result.proofDigest !== proofDigest(input)
      )
        throw new Error("Recorded proof binding mismatch");
      return {
        result,
        commit: {
          transactionId: status.transactionId,
          blockNumber: status.blockNumber.toString(),
          code: status.code,
        },
        timings: {
          endorseMs: endorsed - started,
          submitMs: submitted - endorsed,
          commitWaitMs: finished - submitted,
          recordCommitMs: finished - started,
        },
      };
    },
    async verify(id) {
      const started = performance.now();
      const result = decode(
        await contract.evaluateTransaction("VerifyObservation", id),
      );
      if (
        result.observationId !== id ||
        result.status !== "verified" ||
        typeof result.isNormal !== "boolean" ||
        result.deploymentId !== config.deploymentId
      )
        throw new Error("Invalid verification response");
      return { result, timings: { verifyReadMs: performance.now() - started } };
    },
    close() {
      gateway.close();
      client.close();
    },
  };
}
