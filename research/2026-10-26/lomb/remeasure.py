"""Repeat only online prove/verify after competing jobs finish; preserve first measurements."""

import argparse
import json
import shutil
import statistics
from run import HERE, ROOT, command, dump, write_csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=32)
    args = parser.parse_args()
    directory = HERE / "build" / f"sc{args.count}"
    record = json.loads((directory / "proof_metrics.json").read_text())
    archive = HERE / "evidence" / f"sc{args.count}_first_measurement"
    if archive.exists():
        raise RuntimeError("First-measurement archive already exists; avoid overwriting evidence")
    archive.mkdir(parents=True)
    for pattern in [
        "proof[0-9].json",
        "public[0-9].json",
        "prove*.log",
        "verify*.log",
        "proof_metrics.json",
        "verification_key.json",
    ]:
        for path in directory.glob(pattern):
            shutil.copy2(path, archive / path.name)
    snark = ROOT / "zkp/node_modules/.bin/snarkjs"
    measured = []
    for i in range(3):
        proof_seconds = command(
            [
                snark,
                "groth16",
                "prove",
                directory / "benchmark.zkey",
                directory / "witness.wtns",
                directory / f"proof{i}.json",
                directory / f"public{i}.json",
            ],
            directory / f"prove{i}.log",
        )
        verify_seconds = command(
            [
                snark,
                "groth16",
                "verify",
                directory / "verification_key.json",
                directory / f"public{i}.json",
                directory / f"proof{i}.json",
            ],
            directory / f"verify{i}.log",
        )
        verified = "OK!" in (directory / f"verify{i}.log").read_text()
        assert verified
        measured.append(
            {"repetition": i, "prove_seconds": proof_seconds, "verify_seconds": verify_seconds, "verified": verified}
        )
    durations = [r["prove_seconds"] for r in measured]
    record.update(
        {
            "measurements": measured,
            "prove_seconds_median": statistics.median(durations),
            "prove_seconds_min": min(durations),
            "prove_seconds_max": max(durations),
            "verify_seconds_median": statistics.median([r["verify_seconds"] for r in measured]),
            "timing_note": "Remeasured online prove/verify after competing research jobs finished; first measurements archived.",
        }
    )
    dump(directory / "proof_metrics.json", record)
    rows = json.loads((HERE / "proof_summary.json").read_text())
    rows = [r for r in rows if r["subcarriers"] != args.count] + [record]
    rows.sort(key=lambda r: r["subcarriers"])
    dump(HERE / "proof_summary.json", rows)
    write_csv(HERE / "proof_summary.csv", [{k: v for k, v in r.items() if k != "measurements"} for r in rows])
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
