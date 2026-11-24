#!/usr/bin/env bash
# Run locally by EACH organization's administrator; never copy admin keys between organizations.
set -euo pipefail
ACTION="${1:?install|approve|readiness|commit|query}"
: "${RELEASE_DIR:?Set prepared release directory}"
: "${CORE_PEER_LOCALMSPID:?Set own organization MSP}"
: "${CORE_PEER_MSPCONFIGPATH:?Set own administrator MSP directory}"
: "${CORE_PEER_ADDRESS:?Set own peer DNS:7051}"
: "${CORE_PEER_TLS_ROOTCERT_FILE:?Set own peer TLS CA}"
: "${ORDERER_ENDPOINT:?Set orderer DNS:7050}"
: "${ORDERER_CA:?Set orderer TLS CA}"
export CORE_PEER_TLS_ENABLED=true
MANIFEST="$RELEASE_DIR/deployment/manifest.json"
[[ "$(jq -r '.topology.singleHost' "$MANIFEST")" == false ]] || { echo "External manifest required" >&2; exit 1; }
NAME="$(jq -r '.chaincodeName' "$MANIFEST")"
CHANNEL="$(jq -r '.channelName' "$MANIFEST")"
POLICY="$(jq -r '.topology.endorsementPolicy' "$MANIFEST")"
PACKAGE="$RELEASE_DIR/chaincode.tar.gz"
DEFINITION=(--channelID "$CHANNEL" --name "$NAME" --version "${CC_VERSION:-1.0}" --sequence "${CC_SEQUENCE:-1}" --signature-policy "$POLICY")
ORDERER=(-o "$ORDERER_ENDPOINT" --tls --cafile "$ORDERER_CA")
case "$ACTION" in
  install)
    # Package ONCE, transfer the identical tar.gz to both organizations.
    [[ -f "$PACKAGE" ]] || { echo "Prepare chaincode.tar.gz first (see runbook)" >&2; exit 1; }
    peer lifecycle chaincode install "$PACKAGE"
    peer lifecycle chaincode calculatepackageid "$PACKAGE"
    ;;
  approve)
    PACKAGE_ID="$(peer lifecycle chaincode calculatepackageid "$PACKAGE")"
    peer lifecycle chaincode approveformyorg "${DEFINITION[@]}" "${ORDERER[@]}" --package-id "$PACKAGE_ID"
    ;;
  readiness) peer lifecycle chaincode checkcommitreadiness "${DEFINITION[@]}" --output json ;;
  commit)
    : "${OTHER_PEER_ENDPOINT:?Set the other organization's peer DNS:7051}"
    : "${OTHER_PEER_TLS_CA:?Set the other organization's public TLS CA}"
    peer lifecycle chaincode commit "${DEFINITION[@]}" "${ORDERER[@]}" \
      --peerAddresses "$CORE_PEER_ADDRESS" --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
      --peerAddresses "$OTHER_PEER_ENDPOINT" --tlsRootCertFiles "$OTHER_PEER_TLS_CA"
    ;;
  query) peer lifecycle chaincode querycommitted --channelID "$CHANNEL" --name "$NAME" ;;
  *) echo "Unknown action" >&2; exit 1 ;;
esac
