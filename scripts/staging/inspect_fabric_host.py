"""Read-only Fabric host preflight. No credentials or process arguments are read."""
import argparse
import datetime
import json
import os
import platform
import shutil
import socket
import subprocess
from pathlib import Path


def command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True, help="This host's private IPv4 address")
    parser.add_argument("--ports", nargs="+", type=int, default=[17050, 17051, 17053, 18843])
    parser.add_argument("--loopback-ports", nargs="*", type=int, default=[19443, 19444])
    args = parser.parse_args()
    socket.inet_pton(socket.AF_INET, args.bind)
    if any(port < 1024 or port > 65535 for port in args.ports + args.loopback_ports):
        parser.error("Ports must be 1024..65535")
    system = platform.system()
    memory = None
    if system == "Linux":
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                memory = int(line.split()[1]) * 1024
    elif system == "Darwin":
        value = command("sysctl", "-n", "hw.memsize")
        memory = int(value) if value else None
    checks = []
    listeners = [(args.bind, port) for port in args.ports] + [("127.0.0.1", port) for port in args.loopback_ports]
    for address, port in listeners:
        with socket.socket() as listener:
            try:
                listener.bind((address, port))
                checks.append({"bindIp": address, "port": port, "available": True})
            except OSError as exc:
                checks.append({"bindIp": address, "port": port, "available": False, "error": str(exc)})
    docker = command("docker", "info", "--format", "{{json .ServerVersion}}")
    compose = command("docker", "compose", "version", "--short")
    processes = command("ps", "-axo", "comm=") or ""
    blockers = []
    if platform.machine() not in ("x86_64", "aarch64", "arm64"):
        blockers.append("64-bit amd64/arm64 OS required")
    if not docker:
        blockers.append("Docker daemon unavailable to this account")
    if not compose:
        blockers.append("Docker Compose plugin unavailable")
    if any(not item["available"] for item in checks):
        blockers.append("One or more requested private/loopback listeners cannot bind")
    print(
        json.dumps(
            {
                "checkedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "readOnly": True,
                "os": system,
                "architecture": platform.machine(),
                "logicalCpus": os.cpu_count(),
                "memoryBytes": memory,
                "diskFreeBytes": shutil.disk_usage(Path.home()).free,
                "privateBindIp": args.bind,
                "ports": checks,
                "dockerVersion": json.loads(docker) if docker else None,
                "composeVersion": compose,
                "picoScenesRunning": any(
                    Path(name.strip()).name.lower() == "picoscenes" for name in processes.splitlines()
                ),
                "blockers": blockers,
                "networkDeployed": False,
                "note": "Host preflight only; does not validate inter-host routing, container DNS, certificates or channel health",
            },
            indent=2,
        )
    )
    return 2 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
