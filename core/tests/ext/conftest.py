"""Clave de prueba para firmar paquetes (nunca la de Tepnyx)."""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nyx.ext.signing import public_key_b64, sign_package

TEST_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
TRUSTED = {"prueba-1": public_key_b64(TEST_KEY)}


def signed(path: Path) -> Path:
    sign_package(path, TEST_KEY, "prueba-1")
    return path


def code_files(*tools: str) -> dict[str, bytes]:
    """Lo mínimo de una extensión con herramientas (7.07): su código y su `tools.json`."""
    import json

    specs = [{"name": t, "description": f"Herramienta {t}."} for t in (tools or ("prueba",))]
    return {
        "tools/main.py": b"import nyx\n",
        "tools/tools.json": json.dumps(specs).encode(),
    }
