"""Offline Compose validation. Dummy configuration only; never starts services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    with tempfile.TemporaryDirectory(prefix="csi-compose-check-") as directory:
        base = Path(directory)
        env_file = base / "empty.env"
        env_file.write_text("")
        env = {
            **os.environ,
            "PEER_DNS": "peer.csi.home.arpa", "MSP_ID": "HospitalMSP", "ORDERER_MSP_ID": "OrderingMSP",
            "NODE_IDENTITY_DIR": directory, "ADMIN_TLS_CA_FILE": str(base / "ca.crt"),
            "PRIVATE_BIND_IP": "192.0.2.10", "BRIDGE_ROLE": "reader", "BRIDGE_IDENTITY_DIR": directory,
            "RELEASE_TAG": "validation", "API_ENV_FILE": str(env_file), "WORKER_ENV_FILE": str(env_file),
            "DATABASE_ENV_FILE": str(env_file), "DEPLOYMENT_DIR": directory, "BRIDGE_CA_FILE": str(base / "ca.crt"),
            "ARTIFACT_DIR": directory, "RECORDER_KEY_FILE": str(base / "recorder.key"),
            "PUBLIC_DOMAIN": "csi.home.arpa", "ACME_EMAIL": "validation@example.invalid",
        }
        configs = {}
        for name in ("peer", "orderer", "bridge", "app", "lan"):
            paths = ["app", "lan"] if name == "lan" else [name]
            command = ["docker", "compose", "--env-file", str(env_file)]
            for path in paths:
                command += ["-f", str(ROOT / "deploy/staging" / f"compose.{path}.yml")]
            command += ["config", "--format", "json"]
            configs[name] = json.loads(subprocess.check_output(command, env=env, text=True))
        app = configs["app"]["services"]
        assert all(not app[name].get("ports") for name in ("backend", "worker", "postgres", "gateway", "frontend"))
        assert set(port["target"] for port in app["tls"]["ports"]) == {80, 443}
        assert all("recorder.key" not in volume["target"] for volume in app["backend"]["volumes"])
        assert any(volume["target"] == "/run/secrets/recorder.key" for volume in app["worker"]["volumes"])
        assert all("ADAPTIVE_FABRIC_WRITER_TOKEN" not in app[name]["environment"] for name in ("backend",))
        assert configs["peer"]["services"]["peer"]["environment"]["CORE_PEER_TLS_ENABLED"] == "true"
        assert configs["orderer"]["services"]["orderer"]["environment"]["ORDERER_ADMIN_TLS_ENABLED"] == "true"
        lan_mounts = configs["lan"]["services"]["tls"]["volumes"]
        assert any(volume["source"].endswith("Caddyfile.lan") for volume in lan_mounts)
        print(json.dumps({"composeProfiles": list(configs), "checks": "passed", "servicesStarted": False}))


if __name__ == "__main__":
    main()
