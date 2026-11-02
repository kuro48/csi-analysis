import { test } from "node:test";
import assert from "node:assert/strict";
import {
  stats,
  summarize,
  allocatedInfrastructure,
} from "../benchmark/metrics.mjs";
import { renderReport } from "../benchmark/report.mjs";
test("Median, nearest-rank p95, and absent values", () => {
  assert.equal(stats([8, 2, 3, 1]).median, 2.5);
  assert.equal(stats([8, 2, 3, 1]).p95, 8);
  assert.deepEqual(stats([null, undefined, NaN, -1]), {
    n: 0,
    median: null,
    p95: null,
    min: null,
    max: null,
  });
});
test("Failures counted, warmups excluded, no fake zero measurements", () => {
  const summary = summarize(
    [
      { target: "fabric", warmup: true, status: "verified" },
      { target: "fabric", status: "failed" },
    ],
    "fabric",
    1,
  );
  assert.equal(summary.attempted, 1);
  assert.equal(summary.failed, 1);
  assert.equal(summary.metrics.recordCommitMs.median, null);
  assert.deepEqual(summary.feesWei, []);
});
test("Infrastructure cost requires explicit positive workload", () => {
  assert.equal(allocatedInfrastructure(10, 100), 0.1);
  assert.throws(() => allocatedInfrastructure(10, 0));
});
test("HTML escapes report values and labels absent Sepolia", () => {
  const html = renderReport({
    targets: ["fabric"],
    summaries: [summarize([], "fabric", 1)],
    rows: [],
    metadata: { value: "<script>" },
    inputKind: "<img>",
    runId: "<script>",
    warmup: 1,
    trials: 1,
  });
  assert.ok(html.includes("Sepoliaは未計測"));
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("<img>"));
  assert.ok(html.includes("未計測"));
});
test("Fees from a committed record remain counted when the later verification fails", () => {
  const summary = summarize(
    [
      {
        target: "sepolia",
        status: "failed",
        cost: { gasUsed: "300000", feeWei: "123" },
      },
    ],
    "sepolia",
    1,
  );
  assert.equal(summary.failed, 1);
  assert.equal(summary.metrics.recordCommitMs.median, null);
  assert.deepEqual(summary.feesWei, ["123"]);
  assert.equal(summary.gasUsed.median, 300000);
});
test("A broadcast with unknown receipt is reported as unknown cost", () => {
  const summary = summarize(
    [
      {
        target: "sepolia",
        transactionId: "pending",
        status: "failed",
        cost: {},
      },
    ],
    "sepolia",
    1,
  );
  assert.equal(summary.unknownFeeCount, 1);
  assert.deepEqual(summary.feesWei, []);
});
