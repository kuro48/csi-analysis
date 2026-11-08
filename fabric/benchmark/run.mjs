import {
  readFileSync,
  writeFileSync,
  appendFileSync,
  mkdirSync,
  statSync,
  existsSync,
} from "node:fs";
import { resolve } from "node:path";
import { cpus, totalmem, platform, arch } from "node:os";
import { randomUUID, createHash } from "node:crypto";
import { JsonRpcProvider, Wallet, Contract, id, keccak256 } from "ethers";
import { openGateway } from "../gateway.mjs";
import { summarize, allocatedInfrastructure } from "./metrics.mjs";
import { renderReport } from "./report.mjs";

const root = resolve(import.meta.dirname, "../..");
const config = JSON.parse(
  readFileSync(process.argv[2] || `${root}/.local/fabric/benchmark.json`),
);
const bankBytes = readFileSync(config.fixtures),
  bank = JSON.parse(bankBytes);
const publicSignalCount = bank.publicSignalCount ?? 1;
const isNormalIndex = bank.isNormalIndex ?? 0;
if (!((publicSignalCount === 1 && isNormalIndex === 0) || (publicSignalCount === 70 && isNormalIndex === 1))) throw Error("Unsupported proof bank protocol");
if (bank.samples.some(sample => sample.publicSignals?.length !== publicSignalCount || !["0", "1"].includes(sample.publicSignals[isNormalIndex]))) throw Error("Malformed proof bank outputs");
const targets = config.targets || ["fabric", "sepolia"];
if (
  !Array.isArray(targets) ||
  !targets.length ||
  new Set(targets).size !== targets.length ||
  targets.some((t) => !["fabric", "sepolia", "local-evm"].includes(t))
)
  throw Error("Invalid targets");
if (targets.includes("sepolia") && targets.includes("local-evm"))
  throw Error("Use separate runs for local EVM and Sepolia");
const trials = config.trials ?? 5,
  warmup = config.warmup ?? 1;
if (
  !Number.isInteger(trials) ||
  trials < 1 ||
  !Number.isInteger(warmup) ||
  warmup < 0 ||
  bank.samples.length < trials + warmup
)
  throw Error("Insufficient unique proof fixtures");
const output = resolve(
  config.output || `${root}/.local/fabric/benchmark-${Date.now()}`,
);
if (
  existsSync(resolve(output, "raw.jsonl")) ||
  existsSync(resolve(output, "summary.json"))
)
  throw Error("Output already contains a run; choose a new output directory");
mkdirSync(output, { recursive: true });
const runId = randomUUID(),
  rows = [],
  connections = {},
  metadata = {};
const hash = (data) => createHash("sha256").update(data).digest("hex");
const startedAt = new Date().toISOString();
const report = {
  version: 1,
  runId,
  startedAt,
  inputKind: bank.inputKind,
  proofGenerationScope: bank.proofGenerationScope,
  debugMode: bank.debugMode,
  fixtureBankHash: hash(bankBytes),
  preprocessingMs: bank.preprocessingMs ?? null,
  verificationKeyHash: bank.verificationKeyHash,
  publicSignalCount, isNormalIndex,
  trials,
  warmup,
  concurrency: 1,
  targets,
  metadata,
  rows,
  clientEnvironment: {
    cpu: cpus()[0]?.model,
    memoryBytes: totalmem(),
    platform: platform(),
    architecture: arch(),
    node: process.version,
  },
  notes: [
    bank.inputKind === "synthetic-signal"
      ? "Synthetic inputs are not real patient CSI."
      : "Captured CSI input; preprocessing time reported separately from proof generation.",
    "Fabric Evaluate and EVM eth_call both execute verification as read-only requests. No verification transaction is mined.",
    "Fabric single-host test network is not representative of a geographically distributed production consortium.",
    "Sepolia fees use test ETH, not a real-money price. Infrastructure is excluded unless explicit assumptions are supplied.",
    "Timing boundaries: proof generation separately; record includes commit / configured confirmations; verify includes the read RPC. Startup excluded.",
  ],
  infrastructureAssumptions: null,
};
if (config.infrastructure) {
  const c = config.infrastructure;
  if (
    !targets.includes(c.target) ||
    typeof c.currency !== "string" ||
    !c.currency
  )
    throw Error("Infrastructure requires target and currency");
  report.infrastructureAssumptions = {
    ...c,
    estimatedCostPerOperation: allocatedInfrastructure(
      c.hourlyCost,
      c.operationsPerHour,
    ),
  };
}
async function setup() {
  for (const target of targets) {
    if (target === "fabric") {
      const cfg = JSON.parse(readFileSync(config.fabricGateway));
      const writer = openGateway(cfg, "writer"),
        reader = openGateway(cfg, "reader");
      connections.fabric = { writer, reader };
      const actual = await writer.configuration();
      await reader.configuration();
      if (
        actual.verificationKeyHash !== bank.verificationKeyHash ||
        (actual.publicSignalCount ?? 1) !== publicSignalCount ||
        actual.debugMode !== bank.debugMode
      )
        throw Error("Fabric proof bank configuration mismatch");
      metadata.fabric = {
        deploymentId: actual.deploymentId,
        topology: actual.topology,
        verification: "Gateway evaluateTransaction (single peer)",
        finality: "VALID commit status",
        nativeTransactionFee: "none",
      };
    } else {
      const evm = config.evm,
        manifest = JSON.parse(readFileSync(evm.manifest));
      const rpc = process.env[evm.rpcEnv || "ETHEREUM_RPC_URL"];
      if (!rpc) throw Error("Missing EVM RPC environment variable");
      const provider = new JsonRpcProvider(rpc);
      provider.pollingInterval = 1000;
      connections.evm = { provider };
      const chainId = Number((await provider.getNetwork()).chainId);
      if (
        target === "sepolia"
          ? chainId !== 11155111
          : ![31337, 1337].includes(chainId)
      )
        throw Error("Wrong EVM network for target");
      if (
        chainId !== manifest.chainId ||
        manifest.verificationKeyHash !== bank.verificationKeyHash ||
        manifest.publicSignalCount !== publicSignalCount ||
        manifest.debugMode !== bank.debugMode
      )
        throw Error("EVM proof bank configuration mismatch");
      for (const p of ["registry", "verifier"])
        if (
          keccak256(await provider.getCode(manifest[p + "Address"])) !==
          manifest[p + "CodeHash"]
        )
          throw Error("EVM contract code mismatch");
      if (statSync(evm.recorderKeyFile).mode & 0o077)
        throw Error("Recorder key must be mode 0600");
      const signer = new Wallet(
        readFileSync(evm.recorderKeyFile, "utf8").trim(),
        provider,
      );
      const contract = new Contract(
        manifest.registryAddress,
        manifest.registryAbi,
        signer,
      );
      if (
        signer.address.toLowerCase() !==
          manifest.recorderAddress.toLowerCase() ||
        (await contract.recorder()).toLowerCase() !==
          signer.address.toLowerCase() ||
        (await contract.verifier()).toLowerCase() !==
          manifest.verifierAddress.toLowerCase() ||
        (await contract.debugMode()) !== bank.debugMode
      )
        throw Error("EVM deployment configuration mismatch");
      const confirmations = evm.confirmations ?? 2;
      if (!Number.isInteger(confirmations) || confirmations < 1)
        throw Error("Invalid confirmations");
      connections.evm = { provider, contract, confirmations };
      metadata[target] = {
        chainId,
        registryAddress: manifest.registryAddress,
        confirmations,
        verification: "eth_call at receipt block",
        finality: `receipt + ${confirmations} confirmation(s), not Ethereum finalized`,
      };
    }
  }
}
async function measure(target, payload, sample, row) {
  if (target === "fabric") {
    const { writer, reader } = connections.fabric;
    const recorded = await writer.record(payload);
    Object.assign(row, recorded.timings, {
      transactionId: recorded.result.transactionId,
      blockNumber: recorded.commit.blockNumber,
    });
    if (recorded.result.reused)
      throw Error("Proof already recorded; generate a fresh fixture bank");
    const verified = await reader.verify(payload.observationId);
    if (
      verified.result.patientRef !== payload.patientRef ||
      verified.result.observedAt !== payload.observedAt ||
      verified.result.durationSeconds !== payload.durationSeconds ||
      verified.result.transactionId !== recorded.result.transactionId ||
      verified.result.isNormal !== (sample.publicSignals[isNormalIndex] === "1")
    )
      throw Error("Verification mismatch");
    Object.assign(row, verified.timings, {
      isNormal: verified.result.isNormal,
      cost: {
        gasUsed: null,
        feeWei: null,
        nativeTransactionFee: 0,
        unit: null,
        infrastructureIncluded: false,
      },
    });
  } else {
    const { contract, confirmations } = connections.evm,
      p = sample.proof;
    const args = [
      payload.observationId,
      payload.patientRef,
      payload.observedAt,
      payload.durationSeconds,
      p.pi_a.slice(0, 2),
      [p.pi_b[0].slice().reverse(), p.pi_b[1].slice().reverse()],
      p.pi_c.slice(0, 2),
      sample.publicSignals,
    ];
    // Fee estimation is preflight and excluded from record timing, as is connection setup.
    const gas = await contract.recordObservation.estimateGas(...args);
    const fee = await connections.evm.provider.getFeeData();
    const maxWei = BigInt(config.evm.maxTxWei || "10000000000000000");
    const gasLimit = (gas * 120n) / 100n;
    if (gasLimit * (fee.maxFeePerGas ?? fee.gasPrice) > maxWei)
      throw Error("Transaction fee cap exceeded");
    const start = performance.now();
    const tx = await contract.recordObservation(...args, {
      gasLimit,
      ...(fee.maxFeePerGas
        ? {
            maxFeePerGas: fee.maxFeePerGas,
            maxPriorityFeePerGas: fee.maxPriorityFeePerGas,
          }
        : { gasPrice: fee.gasPrice }),
    });
    row.transactionId = tx.hash;
    const sent = performance.now();
    const receipt = await tx.wait(
      confirmations,
      config.evm.timeoutMs ?? 180000,
    );
    if (!receipt || receipt.status !== 1)
      throw Error("EVM record did not succeed");
    row.recordCommitMs = performance.now() - start;
    row.sendMs = sent - start;
    row.receiptWaitMs = performance.now() - sent;
    row.blockNumber = receipt.blockNumber;
    row.cost = {
      gasUsed: receipt.gasUsed.toString(),
      effectiveGasPriceWei: receipt.gasPrice.toString(),
      feeWei: (receipt.gasUsed * receipt.gasPrice).toString(),
      unit: target === "sepolia" ? "Sepolia test ETH" : "local test ETH",
      infrastructureIncluded: false,
    };
    const block = await connections.evm.provider.getBlock(receipt.blockNumber);
    if (block.hash !== receipt.blockHash)
      throw Error("Receipt block reorganized");
    const vstart = performance.now();
    const normal = await contract.verifyObservation(payload.observationId, {
      blockTag: receipt.blockNumber,
    });
    row.verifyReadMs = performance.now() - vstart;
    if (
      (await connections.evm.provider.getBlock(receipt.blockNumber)).hash !==
        receipt.blockHash ||
      normal !== (sample.publicSignals[isNormalIndex] === "1")
    )
      throw Error("Verification mismatch");
    row.isNormal = normal;
  }
  row.totalMs = row.proofGenerationMs + row.recordCommitMs + row.verifyReadMs;
  row.status = "verified";
}
try {
  await setup();
  for (let i = 0; i < trials + warmup; i++) {
    const sample = bank.samples[i],
      captureId = randomUUID();
    const referenceTime = connections.evm
      ? Math.min(
          Math.floor(Date.now() / 1000),
          (await connections.evm.provider.getBlock("latest")).timestamp,
        )
      : Math.floor(Date.now() / 1000);
    const payload = {
      observationId: id("csi-observation:v1:" + captureId),
      patientRef: id("csi-patient:v1:" + runId),
      observedAt: referenceTime - 61,
      durationSeconds: 60,
      proof: sample.proof,
      publicSignals: sample.publicSignals,
    };
    // Same proof and metadata on both ledgers; alternate submission order each pair.
    for (const target of i % 2 ? targets.slice().reverse() : targets) {
      const row = {
        target,
        trial: i - warmup + 1,
        warmup: i < warmup,
        fixtureIndex: i,
        proofHash: hash(JSON.stringify(sample.proof)),
        proofGenerationMs: sample.proofGenerationMs,
        status: "failed",
        cost: {},
      };
      try {
        await measure(target, payload, sample, row);
      } catch (error) {
        if (
          target !== "fabric" &&
          error.receipt?.gasUsed != null &&
          error.receipt?.gasPrice != null
        ) {
          row.cost = {
            gasUsed: error.receipt.gasUsed.toString(),
            effectiveGasPriceWei: error.receipt.gasPrice.toString(),
            feeWei: (error.receipt.gasUsed * error.receipt.gasPrice).toString(),
            unit: target === "sepolia" ? "Sepolia test ETH" : "local test ETH",
            infrastructureIncluded: false,
          };
        }
        if (target !== "fabric" && row.transactionId && !row.cost.feeWei)
          row.cost.status = "unknown_after_submission";
        row.errorCategory = error.code || error.name;
        row.elapsedFailureAt = new Date().toISOString();
        console.error(`${target}: failed (${row.errorCategory})`);
      }
      rows.push(row);
      appendFileSync(resolve(output, "raw.jsonl"), JSON.stringify(row) + "\n");
      console.log(`${target}: ${row.status} / trial ${row.trial}`);
    }
  }
  report.summaries = targets.map((t) => summarize(rows, t, trials));
  report.completedAt = new Date().toISOString();
  writeFileSync(
    resolve(output, "summary.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  const fields = [
    "target",
    "trial",
    "warmup",
    "status",
    "proofGenerationMs",
    "recordCommitMs",
    "verifyReadMs",
    "totalMs",
    "transactionId",
    "gasUsed",
    "feeWei",
    "effectiveGasPriceWei",
    "errorCategory",
  ];
  writeFileSync(
    resolve(output, "raw.csv"),
    fields.join(",") +
      "\n" +
      rows
        .map((r) =>
          fields
            .map((f) => JSON.stringify(r[f] ?? r.cost?.[f] ?? ""))
            .join(","),
        )
        .join("\n") +
      "\n",
  );
  writeFileSync(resolve(output, "report.html"), renderReport(report));
  console.log(`Report: ${output}/report.html`);
  if (rows.some((r) => r.status !== "verified")) process.exitCode = 1;
} finally {
  connections.fabric?.writer.close();
  connections.fabric?.reader.close();
  connections.evm?.provider.destroy();
}
