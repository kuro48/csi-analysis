import copy
import io
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.api.endpoints import onchain
from app.api.endpoints.breathing import _read_upload
from app.core.access import require_operator
from app.core.config import settings
from app.services.onchain_service import BASE_FIELD, SCALAR_FIELD, ChainUnavailable, OnchainService, parse_proof


@pytest.mark.parametrize("chain_id", [1, 10, 8453, 42161, 0])
def test_mainnet_manifest_rejected_before_rpc(monkeypatch, tmp_path, chain_id):
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps({"chainId": chain_id}))
    monkeypatch.setattr(settings, "ONCHAIN_MANIFEST", str(path))
    with pytest.raises(ChainUnavailable, match="Sepolia"):
        OnchainService()

PROOF = {
    "protocol": "groth16",
    "curve": "bn128",
    "pi_a": ["1", "2", "1"],
    "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
    "pi_c": ["7", "8", "1"],
}


def test_snarkjs_pair_order_and_signal_precision():
    a, b, c, signals = parse_proof(PROOF, [str(SCALAR_FIELD - 1)], 1)
    assert (a, b, c) == ([1, 2], [[4, 3], [6, 5]], [7, 8])
    assert signals == [SCALAR_FIELD - 1]


@pytest.mark.parametrize("signal", ["-1", "01", "1.5", "1e3", str(SCALAR_FIELD), 1, True, None])
def test_invalid_public_fields(signal):
    with pytest.raises(ValueError):
        parse_proof(PROOF, [signal], 1)


def test_invalid_coordinate_and_arity():
    proof = copy.deepcopy(PROOF)
    proof["pi_a"][0] = str(BASE_FIELD)
    with pytest.raises(ValueError):
        parse_proof(proof, ["1"], 1)
    with pytest.raises(ValueError):
        parse_proof(PROOF, ["1", "2"], 1)
    proof["pi_a"] = "121"
    with pytest.raises(ValueError):
        parse_proof(proof, ["1"], 1)


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(onchain.router, prefix="/onchain")
    with TestClient(app) as client:
        yield client, app


def test_unconfigured_status_does_not_expose_rpc(api, monkeypatch):
    monkeypatch.setattr(settings, "ONCHAIN_MANIFEST", "")
    client, _ = api
    response = client.get("/onchain/status")
    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert "rpc" not in response.text.lower()


def test_api_prepare_validation_and_receipt(api):
    client, app = api

    class Service:
        def prepare(self, circuit, proof, signals):
            parse_proof(proof, signals, 1)
            return {"proofId": "0x" + "a" * 64, "alreadyVerified": False, "value": "0x0"}

        def receipt(self, tx_hash):
            return {"transactionHash": tx_hash, "status": "pending", "confirmations": 0}

    app.dependency_overrides[onchain.get_onchain_service] = Service
    response = client.post(
        "/onchain/prepare", json={"circuit": "csi_breathing_certificate", "proof": PROOF, "publicSignals": ["1"]}
    )
    assert response.status_code == 200
    assert response.json()["value"] == "0x0"
    response = client.post(
        "/onchain/prepare", json={"circuit": "csi_breathing_certificate", "proof": PROOF, "publicSignals": ["-1"]}
    )
    assert response.status_code == 422
    assert client.get("/onchain/transactions/invalid").status_code == 422
    response = client.get("/onchain/transactions/0x" + "a" * 64)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_private_research_routes_require_token(monkeypatch):
    from fastapi import Depends

    monkeypatch.setattr(settings, "PUBLIC_MODE", True)
    monkeypatch.setattr(settings, "OPERATOR_API_TOKEN", "a" * 40)
    app = FastAPI()

    @app.get("/research", dependencies=[Depends(require_operator)])
    def research():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/research").status_code == 401
        assert client.get("/research", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/research", headers={"Authorization": "Bearer " + "a" * 40}).json() == {"ok": True}


@pytest.mark.asyncio
async def test_streamed_upload_rejects_over_limit(monkeypatch):
    from fastapi import HTTPException

    from app.api.endpoints import breathing

    monkeypatch.setattr(breathing, "MAX_ANALYSIS_BYTES", 3)
    with pytest.raises(HTTPException) as error:
        await _read_upload(UploadFile(file=io.BytesIO(b"1234"), filename="sample.csi"))
    assert error.value.status_code == 413


def test_receipt_requires_correct_contract_event_canonical_block_and_confirmations(monkeypatch):
    monkeypatch.setattr(settings, "ONCHAIN_CONFIRMATIONS", 3)
    address = "0x" + "a" * 40
    proof_id = b"p" * 32
    receipt = {"to": address, "status": 1, "blockNumber": 10, "blockHash": b"b" * 32, "gasUsed": 340000}
    logs = [{"address": address, "args": {"proofId": proof_id}}]
    eth = SimpleNamespace(
        block_number=11, get_transaction_receipt=lambda _: receipt, get_block=lambda _: {"hash": b"b" * 32}
    )
    record = [b"c" * 32, b"s" * 32, "0x" + "1" * 40, 12345, 10]
    service = OnchainService.__new__(OnchainService)
    service.w3 = SimpleNamespace(eth=eth)
    service.contract = SimpleNamespace(
        address=address,
        events=SimpleNamespace(ProofVerified=lambda: SimpleNamespace(process_receipt=lambda _: logs)),
        functions=SimpleNamespace(records=lambda _: SimpleNamespace(call=lambda: record)),
    )
    assert service.receipt("tx")["status"] == "confirming"
    eth.block_number = 12
    assert service.receipt("tx")["status"] == "confirmed"
    receipt["status"] = 0
    assert service.receipt("tx")["status"] == "reverted"
    receipt["status"] = 1
    receipt["blockHash"] = b"r" * 32
    assert service.receipt("tx")["status"] == "pending"
    receipt["blockHash"] = b"b" * 32
    logs[0]["address"] = "0x" + "f" * 40
    with pytest.raises(ValueError, match="イベント"):
        service.receipt("tx")
    receipt["to"] = "0x" + "f" * 40
    with pytest.raises(ValueError, match="コントラクト"):
        service.receipt("tx")
