import pytest

from app.services.vmd_approx_service import VmdApproxService


def make_service(tmp_path):
    s = object.__new__(VmdApproxService)
    s.N = 128
    s.circuit_name = "csi_vmd_approx"
    s.build_dir = tmp_path
    s.keys_dir = tmp_path
    return s


@pytest.mark.parametrize("wave", [[0] * 127, [0.0] * 128, [True] * 128, [101] * 128])
@pytest.mark.asyncio
async def test_input_validation(tmp_path, wave):
    with pytest.raises(ValueError):
        await VmdApproxService.generate_proof(make_service(tmp_path), wave)


@pytest.mark.asyncio
async def test_missing_artifacts(tmp_path):
    s = make_service(tmp_path)
    s._circuit_build_is_stale = lambda *_: True
    with pytest.raises(FileNotFoundError):
        await s.generate_proof([0] * 128)


@pytest.mark.asyncio
async def test_valid_result_and_verify(tmp_path):
    s = make_service(tmp_path)
    s._circuit_build_is_stale = lambda *_: False
    called = {}

    async def runner(data, verify=False):
        called["verify"] = verify
        called["input"] = data
        return ({"p": 1}, [0, 16, 0, "12345", "777"], True, {})

    s._generate_proof_with_benchmark = runner
    s._performance_from_benchmark = lambda x: {}
    result = await s.generate_proof([0] * 128, parent_commitment="777")
    assert result["estimatedBpm"] == 15
    assert result["intermediateHash"]["value"] == "12345"
    assert result["intermediateHash"]["algorithm"] == "poseidon-bn254"
    assert result["parentCommitment"] == "777"
    assert called["input"]["parentCommitment"] == "777"
    assert 0 < called["input"]["commitmentNonce"] < 2**128
    assert called["verify"] is True


@pytest.mark.parametrize(
    "signals",
    [
        [],
        [0],
        [2, 16, 0, 1, 0],
        [1, 64, 0, 1, 0],
        [1, 16, 3, 1, 0],
        [1, 16, 0, "not-a-field-element", 0],
    ],
)
@pytest.mark.asyncio
async def test_bad_public_signals(tmp_path, signals):
    s = make_service(tmp_path)
    s._circuit_build_is_stale = lambda *_: False

    async def fake(*args, **kwargs):
        return {}, signals, True, {}

    s._generate_proof_with_benchmark = fake
    with pytest.raises(RuntimeError):
        await s.generate_proof([0] * 128)


@pytest.mark.asyncio
async def test_invalid_proof_rejected(tmp_path):
    s = make_service(tmp_path)
    s._circuit_build_is_stale = lambda *_: False

    async def fake(*args, **kwargs):
        return {}, [1, 16, 0, "12345", "0"], False, {}

    s._generate_proof_with_benchmark = fake
    with pytest.raises(RuntimeError, match="verification"):
        await s.generate_proof([0] * 128)
