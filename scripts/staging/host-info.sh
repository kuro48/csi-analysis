#!/usr/bin/env bash
# Read-only inventory for operator-supplied machines. Does not read credentials.
set -euo pipefail
uname -sm
if [[ "$(uname -s)" == Darwin ]]; then
  sysctl hw.memsize machdep.cpu.brand_string hw.logicalcpu
else
  cat /etc/os-release
  lscpu | sed -n '1,18p'
  free -h
fi
df -h .
if command -v docker >/dev/null; then
  docker info --format 'Docker={{.ServerVersion}} architecture={{.Architecture}} CPUs={{.NCPU}} memoryBytes={{.MemTotal}}' || true
  docker compose version || true
fi
