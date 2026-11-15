r"""Empaqueta y firma las extensiones oficiales para meterlas en Nyx (tarea 7.14).

    uv run python scripts/pack_official.py --out ..\dist\app\core\extensiones

Lo llama `scripts/build-release.ps1`. Cada carpeta de `extensions/` se comprueba como al
instalarla, se empaqueta sin sus pruebas y se firma con la clave de Tepnyx (la privada, en
`%LOCALAPPDATA%\Tepnyx\keys\`, nunca en git). Después se comprueba la firma con las claves que
lleva Nyx dentro: si no casan, no se sigue (una oficial sin firma buena no se podría instalar).
Nunca sobrescribe: la carpeta de salida tiene que estar vacía o no existir.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nyx.ext.manifest import MANIFEST_NAME
from nyx.ext.official import pack_folder, source_dir
from nyx.ext.signing import TRUSTED_KEYS, SignatureError, sign_package, verify_package
from nyx.ext.store import PackageError, read_package
from scripts.sign_extension import load_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--id", default="tepnyx-1", help="id de la clave con la que se firma")
    parser.add_argument("--clave", type=Path, help="ruta de la clave privada (PEM)")
    args = parser.parse_args()

    source = source_dir()
    if source is None:
        sys.exit("No encuentro la carpeta extensions/ del repositorio")
    if args.out.exists() and any(args.out.iterdir()):
        sys.exit(f"{args.out} no está vacía: no sobrescribo nada")
    if args.id not in TRUSTED_KEYS:
        sys.exit(f"Nyx no confía en la clave «{args.id}» (TRUSTED_KEYS en nyx/ext/signing.py)")
    try:
        key = load_key(args.id, args.clave)
    except OSError as e:
        sys.exit(f"No encuentro la clave privada «{args.id}»: {e}")
    args.out.mkdir(parents=True, exist_ok=True)
    for folder in sorted(p.parent for p in source.glob(f"*/{MANIFEST_NAME}")):
        out = args.out / f"{folder.name}.nyxext"
        try:
            pack_folder(folder, out)
            manifest, members = read_package(out)
            sign_package(out, key, args.id)
            verify_package(out, trusted=TRUSTED_KEYS)
        except (PackageError, SignatureError) as e:
            sys.exit(f"{folder.name}: {e}")
        print(f"{manifest.id} {manifest.version}: empaquetada y firmada ({len(members)} archivos)")


if __name__ == "__main__":
    main()
