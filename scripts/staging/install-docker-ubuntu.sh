#!/usr/bin/env bash
# Operator-run bootstrap using Docker's official signed Ubuntu APT repository.
# No reboot, package removal, daemon.json edits, or CSI service changes.
set -euo pipefail
MODE="${1:---check}"
[[ "$MODE" == --check || "$MODE" == --install ]] || { echo 'Usage: install-docker-ubuntu.sh --check|--install'; exit 2; }
[[ "$(uname -s)" == Linux && -r /etc/os-release ]] || { echo 'Ubuntu Linux required'; exit 2; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" =~ ^(22\.04|24\.04|26\.04)$ ]] || { echo 'Supported: Ubuntu 22.04/24.04/26.04 LTS'; exit 2; }
CSI_ARCH="$(dpkg --print-architecture)"
[[ "$CSI_ARCH" == amd64 || "$CSI_ARCH" == arm64 ]] || { echo '64-bit amd64 or arm64 required'; exit 2; }
echo "OS=$PRETTY_NAME architecture=$CSI_ARCH"
if [[ "$MODE" == --check ]]; then
  if command -v docker >/dev/null; then
    docker --version
    docker compose version || true
    docker info --format 'Server={{.ServerVersion}}' || true
  else
    echo 'Docker is absent. An operator must run sudo bash install-docker-ubuntu.sh --install.'
  fi
  exit 0
fi
[[ "$EUID" == 0 ]] || { echo 'Run with sudo; do not send passwords to chat.'; exit 2; }
CSI_USER="${SUDO_USER:-}"
[[ "$CSI_USER" =~ ^[a-z_][a-z0-9_-]*$ && "$CSI_USER" != root ]] || { echo 'Run sudo from the intended non-root operator account.'; exit 2; }
id "$CSI_USER" >/dev/null
if ! command -v docker >/dev/null; then
  # Do not remove packages that may belong to another running application.
  for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
    if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" == 'install ok installed' ]]; then
      echo "Conflicting package installed: $package. Review existing workloads first."; exit 2
    fi
  done
  if [[ -e /etc/apt/sources.list.d/docker.list || -e /etc/apt/sources.list.d/docker.sources ]]; then
    echo 'Existing Docker APT configuration found; inspect it instead of adding a duplicate.'; exit 2
  fi
  apt-get update
  apt-get install -y ca-certificates curl
  install -d -m 0755 /etc/apt/keyrings
  CSI_TMP="$(mktemp -d)"
  trap 'rm -rf "$CSI_TMP"' EXIT
  curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
    https://download.docker.com/linux/ubuntu/gpg -o "$CSI_TMP/docker.asc"
  install -m 0644 "$CSI_TMP/docker.asc" /etc/apt/keyrings/csi-docker.asc
  cat > "$CSI_TMP/docker.sources" <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $CSI_ARCH
Signed-By: /etc/apt/keyrings/csi-docker.asc
EOF
  if [[ -e /etc/apt/sources.list.d/csi-docker.sources ]] && ! cmp -s "$CSI_TMP/docker.sources" /etc/apt/sources.list.d/csi-docker.sources; then
    echo 'Existing CSI Docker repository differs; inspect before replacing it.'; exit 2
  fi
  install -m 0644 "$CSI_TMP/docker.sources" /etc/apt/sources.list.d/csi-docker.sources
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version
systemctl enable --now docker
# Docker group access is privileged; grant only to the sudo operator running this script.
usermod -aG docker "$CSI_USER"
docker info --format 'Docker={{.ServerVersion}} architecture={{.Architecture}}'
echo "Installed. Reconnect SSH as $CSI_USER, then run docker info and docker compose version."
