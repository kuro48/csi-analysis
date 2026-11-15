#!/usr/bin/env python3
"""Persist environment versions and source provenance for replay of this experiment."""

import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path("/home/infonetworking/csi-zkp")
names = ["pip", "setuptools", "wheel", "Cython", "numpy", "scipy", "picoscenes"]
versions = {name: importlib.metadata.version(name) for name in names}
freeze = subprocess.check_output([sys.executable, "-m", "pip", "freeze", "--all"], text=True)
(ROOT / "results/python-freeze.txt").write_text(freeze)
source = ROOT / "sources/PicoScenes-Python-Toolbox"
inventory = dict(host=platform.node(), python=sys.version, executable=sys.executable,
                 node=subprocess.check_output(["node", "--version"], text=True).strip(),
                 npm=subprocess.check_output(["npm", "--version"], text=True).strip(),
                 uv=subprocess.check_output(["uv", "--version"], text=True).strip(),
                 packages=versions,
                 parser_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
                 parser_submodules=subprocess.check_output(["git", "submodule", "status", "--recursive"], cwd=source, text=True).strip(),
                 environment_script=str(ROOT / "env.sh"),
                 package_dir=str(ROOT / "packages/lomb_scargle_e2e"))
(ROOT / "results/environment.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
print(json.dumps(inventory, ensure_ascii=False, indent=2))
print(freeze)
