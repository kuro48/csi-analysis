export function stats(values) {
  const sorted = values
    .filter((v) => Number.isFinite(v) && v >= 0)
    .sort((a, b) => a - b);
  if (!sorted.length)
    return { n: 0, median: null, p95: null, min: null, max: null };
  const n = sorted.length;
  return {
    n,
    median:
      n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2,
    p95: sorted[Math.ceil(n * 0.95) - 1],
    min: sorted[0],
    max: sorted[n - 1],
  };
}
export function summarize(rows, target, expected) {
  const runs = rows.filter((r) => r.target === target && !r.warmup);
  const ok = runs.filter((r) => r.status === "verified");
  return {
    target,
    attempted: runs.length,
    expected,
    succeeded: ok.length,
    failed: runs.length - ok.length,
    unknownFeeCount:
      target === "fabric"
        ? 0
        : runs.filter((r) => r.transactionId && r.cost?.feeWei == null).length,
    metrics: Object.fromEntries(
      ["proofGenerationMs", "recordCommitMs", "verifyReadMs", "totalMs"].map(
        (k) => [k, stats(ok.map((r) => r[k]))],
      ),
    ),
    gasUsed: stats(
      runs.map((r) => (r.cost?.gasUsed == null ? NaN : Number(r.cost.gasUsed))),
    ),
    feesWei: runs
      .filter((r) => r.cost?.feeWei != null)
      .map((r) => r.cost.feeWei),
  };
}
export function allocatedInfrastructure(hourlyCost, operationsPerHour) {
  if (
    !Number.isFinite(hourlyCost) ||
    hourlyCost < 0 ||
    !Number.isFinite(operationsPerHour) ||
    operationsPerHour <= 0
  )
    throw Error("Invalid cost assumptions");
  return hourlyCost / operationsPerHour;
}
