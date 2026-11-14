"""Firmar extensiones y la lista de revocación con la clave de Tepnyx (tarea 7.08).

La clave privada vive fuera del repositorio, en `%LOCALAPPDATA%\\Tepnyx\\keys\\` del equipo que
firma (Local: nunca viaja con el perfil), o donde diga `--clave`. Nunca se sube a git ni se
copia a otro sitio.

    uv run python scripts/sign_extension.py --nueva-clave tepnyx-1
        Crea la clave (si no existe) y enseña la línea para `TRUSTED_KEYS` en
        `nyx/ext/signing.py`.
    uv run python scripts/sign_extension.py paquete.nyxext
        Revisa el paquete como lo haría Nyx y lo firma.
    uv run python scripts/sign_extension.py --revocadas revocadas.json
        Firma la lista de revocación (escribe revocadas.sig al lado).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nyx.ext.signing import (
    RevocationList,
    public_key_b64,
    sign_package,
    sign_revocations,
    verify_package,
)
from nyx.ext.store import PackageError, read_package


def keys_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Tepnyx" / "keys"


def key_path(key_id: str) -> Path:
    return keys_dir() / f"extensiones-{key_id}.pem"


def new_key(key_id: str) -> None:
    path = key_path(key_id)
    if path.exists():
        sys.exit(f"Ya existe {path}: no la sobrescribo. Usa otro id para una clave nueva.")
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    # Creación exclusiva: nunca pisa nada.
    with open(path, "xb") as f:
        f.write(pem)
    print(f"Clave privada en {path}. Guárdala con copia de seguridad y fuera de git.")
    print("Añade esto a TRUSTED_KEYS en nyx/ext/signing.py:")
    print(f'    "{key_id}": "{public_key_b64(key)}",')


def load_key(key_id: str, path: Path | None) -> Ed25519PrivateKey:
    path = path or key_path(key_id)
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        sys.exit("La clave no es Ed25519")
    return key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paquete", nargs="?", type=Path)
    parser.add_argument("--nueva-clave", metavar="ID")
    parser.add_argument("--id", default="tepnyx-1", help="id de la clave con la que se firma")
    parser.add_argument("--clave", type=Path, help="ruta de la clave privada (PEM)")
    parser.add_argument("--revocadas", type=Path, help="lista de revocación a firmar")
    args = parser.parse_args()

    if args.nueva_clave:
        new_key(args.nueva_clave)
        return
    key = load_key(args.id, args.clave)
    trusted = {args.id: public_key_b64(key)}
    if args.revocadas:
        raw = args.revocadas.read_bytes()
        RevocationList.model_validate_json(raw)  # que sea una lista válida antes de firmar
        args.revocadas.with_suffix(".sig").write_bytes(sign_revocations(raw, key, args.id))
        print(f"Firmada: {args.revocadas.with_suffix('.sig')}")
        return
    if args.paquete is None:
        parser.error("falta el paquete")
    try:
        manifest, _ = read_package(args.paquete)  # las mismas comprobaciones que hace Nyx
    except PackageError as e:
        sys.exit(f"No se firma: {e}")
    sign_package(args.paquete, key, args.id)
    verify_package(args.paquete, trusted=trusted)
    print(f"Firmada {manifest.id} {manifest.version} con la clave {args.id}.")


if __name__ == "__main__":
    main()
