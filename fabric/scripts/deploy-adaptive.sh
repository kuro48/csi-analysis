#!/usr/bin/env bash
# Separate chaincode namespace; preserves the existing observation ledger.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export FABRIC_WORK_DIR="${FABRIC_WORK_DIR:-$ROOT/.local/fabric-adaptive}"
export FABRIC_NETWORK_DIR="${FABRIC_NETWORK_DIR:-$ROOT/.local/fabric/fabric-samples/test-network}"
export FABRIC_CHAINCODE_NAME="csiadaptive4004"
export ADAPTIVE_ARTIFACT_MANIFEST="${ADAPTIVE_ARTIFACT_MANIFEST:-$ROOT/.local/circom-adaptive-4004/artifacts.json}"
: "${FABRIC_VKEY:?Set FABRIC_VKEY to the new 4004-candidate verification key}"
node "$ROOT/fabric/scripts/prepare-chaincode.mjs"
cd "$FABRIC_NETWORK_DIR"
if [[ "${FABRIC_RESUME:-false}" == true ]]; then
  # Resume an interrupted lifecycle operation without reapproving unchanged content.
  # Both peers must already have the identical package installed.
  export PATH="$FABRIC_NETWORK_DIR/../bin:$PATH"
  export FABRIC_CFG_PATH="$FABRIC_NETWORK_DIR/../config"
  export TEST_NETWORK_HOME="$FABRIC_NETWORK_DIR" OVERRIDE_ORG="" VERBOSE=false
  source scripts/envVar.sh
  PACKAGE_ID="$(peer lifecycle chaincode calculatepackageid "$FABRIC_CHAINCODE_NAME.tar.gz")"
  DEFINITION=(--channelID csi --name "$FABRIC_CHAINCODE_NAME" --version "${FABRIC_CC_VERSION:-1.0}"
    --sequence "${FABRIC_CC_SEQUENCE:-1}" --signature-policy "AND('Org1MSP.peer','Org2MSP.peer')")
  ORDERER=(-o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA")
  for org in 1 2; do
    setGlobals "$org"
    readiness="$(peer lifecycle chaincode checkcommitreadiness "${DEFINITION[@]}" --output json)"
    if [[ "$(jq -r --arg org "Org${org}MSP" '.approvals[$org]' <<< "$readiness")" != true ]]; then
      peer lifecycle chaincode approveformyorg "${DEFINITION[@]}" "${ORDERER[@]}" --package-id "$PACKAGE_ID"
    fi
  done
  setGlobals 1
  peer lifecycle chaincode commit "${DEFINITION[@]}" "${ORDERER[@]}" \
    --peerAddresses localhost:7051 --tlsRootCertFiles "$PEER0_ORG1_CA" \
    --peerAddresses localhost:9051 --tlsRootCertFiles "$PEER0_ORG2_CA"
  for org in 1 2; do
    setGlobals "$org"
    peer lifecycle chaincode querycommitted --channelID csi --name "$FABRIC_CHAINCODE_NAME"
  done
  exit 0
fi
bash network.sh deployCC -c csi -ccn "$FABRIC_CHAINCODE_NAME" \
  -ccp "$FABRIC_WORK_DIR/chaincode" -ccl javascript \
  -ccv "${FABRIC_CC_VERSION:-1.0}" -ccs "${FABRIC_CC_SEQUENCE:-1}" \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')"
