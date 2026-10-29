"""Regression checks against compiled WASM, including constrained bad inputs."""

import json
import subprocess
from run import HERE, ROOT, dump, witness


def main():
    source = sorted((HERE / "inputs").glob("csi_*_sc1.json"))[0]
    original = json.loads(source.read_text())
    results = []
    invalid = {**original, "timestampsMs": list(original["timestampsMs"])}
    invalid["timestampsMs"][1] = invalid["timestampsMs"][0]
    path = HERE / "inputs/invalid_timestamp.json"
    dump(path, invalid)
    try:
        witness(1, path)
    except RuntimeError as e:
        results.append({"case": "non_increasing_timestamp", "rejected": True, "error_excerpt": str(e)[:300]})
    else:
        raise AssertionError("Invalid timestamp accepted")
    invalid = {**original, "csiI": [[2048] for _ in range(64)], "csiQ": [[2048] for _ in range(64)]}
    path = HERE / "inputs/invalid_constant.json"
    dump(path, invalid)
    try:
        witness(1, path)
    except RuntimeError as e:
        results.append({"case": "constant_magnitude_subcarrier", "rejected": True, "error_excerpt": str(e)[:300]})
    else:
        raise AssertionError("Zero signal norm accepted")
    evidence = HERE / "build/sc1"
    if (evidence / "proof0.json").exists():
        public = json.loads((evidence / "public0.json").read_text())
        public[3] = str((int(public[3]) + 1) % 32)
        path = HERE / "inputs/tampered_public.json"
        dump(path, public)
        result = subprocess.run(
            [
                str(ROOT / "zkp/node_modules/.bin/snarkjs"),
                "groth16",
                "verify",
                str(evidence / "verification_key.json"),
                str(path),
                str(evidence / "proof0.json"),
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode != 0 and "Invalid proof" in result.stdout, result.stdout + result.stderr
        results.append({"case": "tampered_public_frequency_bin", "rejected": True})
    dump(HERE / "validation.json", results)
    print(results)


if __name__ == "__main__":
    main()
