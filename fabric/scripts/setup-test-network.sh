#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${FABRIC_WORK_DIR:-$ROOT/.local/fabric}"
SAMPLES_COMMIT=5789681b4f4d24e58fa40f19a69f5496892374b6
FABRIC_COMMIT=f871cf92a026aba7b12e6f06d71ded3e6e659d71
command -v docker >/dev/null
docker info >/dev/null
mkdir -p "$WORK"
if [[ ! -d "$WORK/fabric-samples/.git" ]]; then
 git clone https://github.com/hyperledger/fabric-samples.git "$WORK/fabric-samples"
 git -C "$WORK/fabric-samples" checkout "$SAMPLES_COMMIT"
fi
[[ "$(git -C "$WORK/fabric-samples" rev-parse HEAD)" == "$SAMPLES_COMMIT" ]] || { echo 'Unexpected fabric-samples version'; exit 1; }
if [[ ! -x "$WORK/fabric-samples/bin/peer" ]]; then
 curl --fail --location "https://raw.githubusercontent.com/hyperledger/fabric/$FABRIC_COMMIT/scripts/install-fabric.sh" -o "$WORK/install-fabric.sh"
 (cd "$WORK" && bash install-fabric.sh --fabric-version 2.5.16 --ca-version 1.5.15 binary docker)
fi
npm ci --prefix "$ROOT/fabric"
npm ci --prefix "$ROOT/fabric/chaincode"
cd "$WORK/fabric-samples/test-network"
if [[ ! -f channel-artifacts/csi.block ]]; then
 bash network.sh up createChannel -c csi -i 2.5.16
fi
node "$ROOT/fabric/scripts/prepare-chaincode.mjs"
bash network.sh deployCC -c csi -ccn csiobservations -ccp "$WORK/chaincode" -ccl javascript -ccv "${FABRIC_CC_VERSION:-1.0}" -ccs "${FABRIC_CC_SEQUENCE:-1}" -ccep "AND('Org1MSP.peer','Org2MSP.peer')"
