#!/usr/bin/env python3
"""Create host-local offline PKI for the two-host Fabric experiment.

Run independently on each host. Transfer only public/ to other hosts.
This is a manual experimental issuer, not a managed Fabric CA service.
Never reuse this identity tree for a production deployment.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def openssl(*args: str) -> None:
    subprocess.run(["openssl", *map(str, args)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def ca(directory: Path, name: str) -> None:
    directory.mkdir(parents=True)
    config = directory / "ca.cnf"
    config.write_text(
        "[req]\ndistinguished_name=dn\nx509_extensions=ca\nprompt=no\n"
        f"[dn]\nCN={name}\n[ca]\nbasicConstraints=critical,CA:TRUE,pathlen:0\n"
        "keyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n"
    )
    openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", directory / "ca.key")
    openssl(
        "req",
        "-new",
        "-x509",
        "-sha256",
        "-days",
        "365",
        "-key",
        directory / "ca.key",
        "-config",
        config,
        "-out",
        directory / "ca.crt",
    )


def issue(authority: Path, target: Path, name: str, role: str, dns: str | None = None) -> None:
    target.mkdir(parents=True)
    openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", target / "key.pem")
    openssl(
        "req",
        "-new",
        "-sha256",
        "-key",
        target / "key.pem",
        "-subj",
        f"/CN={name}/OU={role}",
        "-out",
        target / "request.pem",
    )
    extensions = "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
    extensions += "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n"
    if dns:
        extensions += f"extendedKeyUsage=serverAuth,clientAuth\nsubjectAltName=DNS:{dns}\n"
    elif role == "admin-tls":
        extensions += "extendedKeyUsage=clientAuth\n"
    (target / "extensions.cnf").write_text(extensions)
    openssl(
        "x509",
        "-req",
        "-sha256",
        "-days",
        "180",
        "-in",
        target / "request.pem",
        "-CA",
        authority / "ca.crt",
        "-CAkey",
        authority / "ca.key",
        "-set_serial",
        "0x" + os.urandom(16).hex(),
        "-extfile",
        target / "extensions.cnf",
        "-out",
        target / "cert.pem",
    )
    openssl("verify", "-CAfile", authority / "ca.crt", target / "cert.pem")


def msp(target: Path, authority: Path, tls_authority: Path, identity: Path | None = None) -> None:
    for folder in ["cacerts", "tlscacerts"]:
        (target / folder).mkdir(parents=True)
    shutil.copyfile(authority / "ca.crt", target / "cacerts/ca.crt")
    shutil.copyfile(tls_authority / "ca.crt", target / "tlscacerts/ca.crt")
    config = {
        "NodeOUs": {
            "Enable": True,
            **{
                f"{role.title()}OUIdentifier": {"Certificate": "cacerts/ca.crt", "OrganizationalUnitIdentifier": role}
                for role in ["client", "peer", "admin", "orderer"]
            },
        }
    }
    (target / "config.yaml").write_text(json.dumps(config, indent=2) + "\n")
    if identity:
        for folder in ["signcerts", "keystore"]:
            (target / folder).mkdir()
        shutil.copyfile(identity / "cert.pem", target / "signcerts/cert.pem")
        shutil.copyfile(identity / "key.pem", target / "keystore/key.pem")


def bootstrap(destination: Path, msp_id: str, dns: str, node_role: str, bridge_role: str | None) -> None:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,63}", msp_id):
        raise ValueError("Invalid MSP ID")
    if not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?", dns) or "." not in dns:
        raise ValueError("Expected DNS hostname")
    if node_role not in {"peer", "orderer"} or (node_role == "orderer" and bridge_role):
        raise ValueError("Only peers have a bridge identity")
    os.umask(0o077)
    destination.mkdir(parents=True, exist_ok=False)
    signing, tls = destination / "ca/signing", destination / "ca/tls"
    ca(signing, msp_id + "-signing")
    ca(tls, msp_id + "-tls")
    for name, role in [("node", node_role), ("admin", "admin")]:
        identity = destination / "issued" / name
        issue(signing, identity, msp_id + "-" + name, role)
        msp(destination / name / "msp", signing, tls, identity)
    msp(destination / "public" / msp_id / "msp", signing, tls)
    node_tls = destination / "issued/node-tls"
    issue(tls, node_tls, dns, node_role, dns)
    tls_dir = destination / "node/tls"
    tls_dir.mkdir()
    for source, name in [
        (node_tls / "cert.pem", "server.crt"),
        (node_tls / "key.pem", "server.key"),
        (tls / "ca.crt", "ca.crt"),
    ]:
        shutil.copyfile(source, tls_dir / name)
    if node_role == "orderer":
        public_orderers = destination / "public/orderers"
        public_orderers.mkdir()
        shutil.copyfile(node_tls / "cert.pem", public_orderers / (dns + ".crt"))
        admin_ca = destination / "ca/admin-tls"
        ca(admin_ca, msp_id + "-admin-tls")
        issue(admin_ca, destination / "admin-tls", msp_id + "-admin-tls", "admin-tls")
    if bridge_role:
        identity = destination / "issued/bridge"
        issue(signing, identity, msp_id + "-" + bridge_role, "client")
        bridge = destination / "bridge"
        bridge.mkdir()
        shutil.copyfile(identity / "cert.pem", bridge / "client.crt")
        shutil.copyfile(identity / "key.pem", bridge / "client.key")
        shutil.copyfile(tls / "ca.crt", bridge / "peer-ca.crt")
        bridge_tls = destination / "issued/bridge-tls"
        issue(tls, bridge_tls, dns + "-bridge", "client", dns)
        (bridge / "tls").mkdir()
        shutil.copyfile(bridge_tls / "cert.pem", bridge / "tls/server.crt")
        shutil.copyfile(bridge_tls / "key.pem", bridge / "tls/server.key")
        (bridge / "bridge.token").write_text(os.urandom(32).hex() + "\n")
        if bridge_role == "writer":
            shutil.copyfile(identity / "cert.pem", destination / "public/recorder.crt")
    # Only this allowlisted subtree is suitable for exchange. It contains no keys.
    for item in (destination / "public").rglob("*"):
        item.chmod(0o755 if item.is_dir() else 0o644)
    (destination / "public").chmod(0o755)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--msp-id", required=True)
    parser.add_argument("--dns", required=True)
    parser.add_argument("--node-role", choices=["peer", "orderer"], default="peer")
    parser.add_argument("--bridge-role", choices=["reader", "writer"])
    args = parser.parse_args()
    bootstrap(args.destination, args.msp_id, args.dns, args.node_role, args.bridge_role)
    print(json.dumps({"created": str(args.destination), "mspId": args.msp_id, "networkDeployed": False}))
