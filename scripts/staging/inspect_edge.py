"""Read-only Linux edge inventory; never reads CSI, credentials, or process arguments."""
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    root = Path.home() / "csi-zkp"
    memory = {
        line.split(":")[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"))
    }
    cpu = next(
        line.split(":", 1)[1].strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines()
        if line.startswith("model name")
    )
    release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    python = root / "venv/bin/python"
    nodes = sorted((root / "tools").glob("node-*/bin/node"))
    processes = command("ps", "-eo", "comm=") or ""
    print(json.dumps({
        "checkedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "readOnly": True,
        "architecture": platform.machine(),
        "os": release.get("PRETTY_NAME", "").strip('"'),
        "cpu": cpu,
        "logicalCpus": os.cpu_count(),
        "memoryBytes": memory,
        "diskFreeBytes": shutil.disk_usage(root).free,
        "edgeRoot": str(root),
        "python": command(str(python), "--version") if python.exists() else None,
        "node": [{"path": str(node), "version": command(str(node), "--version")} for node in nodes],
        "dockerOnPath": shutil.which("docker"),
        "picoScenesRunning": any(name.strip().lower() == "picoscenes" for name in processes.splitlines()),
        "legacyPackagePresent": (root / "packages/lomb_scargle_e2e").is_dir(),
        "newProofGenerated": False,
        "captureFilesRead": False,
    }, indent=2))


if __name__ == "__main__":
    main()
