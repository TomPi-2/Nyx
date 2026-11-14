"""Herramienta para hacer extensiones de Nyx (adelanto de la tarea 7.12).

    uv run python scripts/nyx_ext.py new carpeta --id autor.nombre --tipo knowledge
        Crea una extensión de ejemplo del tipo pedido (actions, knowledge, preset,
        personality o shape).
    uv run python scripts/nyx_ext.py validate carpeta
        Comprueba el manifiesto y el contenido como lo haría Nyx al instalarla.
    uv run python scripts/nyx_ext.py pack carpeta [-o salida.nyxext]
        La empaqueta (si valida) en un .nyxext listo para firmar (`sign_extension.py`) o para
        instalar en modo desarrollador.

Las extensiones con código (herramientas en Python) llegarán con el SDK cuando exista el host
aislado (7.05–7.07).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nyx.ext.content import load_content
from nyx.ext.manifest import MANIFEST_NAME, ManifestError, load_manifest
from nyx.ext.store import PackageError, read_package

SKIP = {".git", "__pycache__", ".DS_Store", "Thumbs.db"}

EXAMPLES: dict[str, dict[str, object]] = {
    "knowledge": {
        "knowledge/guia.md": "# Guía\n\n## Primeros pasos\n\nCuenta aquí lo que Nyx debe saber.\n"
    },
    "actions": {
        "actions.json": {
            "apps": [
                {
                    "name": "Mi app",
                    "processes": ["miapp.exe"],
                    "names": ["mi app"],
                    "actions": {
                        "save": {"label": "Guardar", "keys": {"es": "ctrl+g", "en": "ctrl+s"}}
                    },
                }
            ]
        }
    },
    "preset": {
        "presets/tranquila.json": {
            "name": "Tranquila",
            "description": "Habla más despacio y en tono neutro.",
            "settings": {"tts": {"speed": 0.9}, "responses": {"tone": "neutro"}},
        }
    },
    "personality": {
        "personality.json": {
            "name": "Mi personalidad",
            "tone": "divertido",
            "phrases": {"thanks": ["¡A mandar!", "¡Para eso estoy!"]},
        }
    },
    "shape": {
        "shape/shape.json": {"name": "Círculo", "box": 1.0},
        "shape/shape.glsl": (
            "void main() {\n"
            "  vec2 p = gl_FragCoord.xy - nyx_resolution * 0.5;\n"
            "  float d = length(p) - nyx_size * 0.42 * nyx_appear * (1.0 + 0.08 * nyx_audio);\n"
            "  float a = clamp(0.5 - d, 0.0, 1.0);\n"
            "  gl_FragColor = vec4(nyx_color * a, a);\n"
            "}\n"
        ),
    },
}


def new(folder: Path, ext_id: str, kind: str) -> None:
    if folder.exists() and any(folder.iterdir()):
        sys.exit(f"{folder} no está vacía: no sobrescribo nada")
    manifest = {
        "id": ext_id,
        "name": ext_id.split(".", 1)[-1].replace("-", " ").capitalize(),
        "version": "0.1.0",
        "author": ext_id.split(".", 1)[0],
        "description": "",
        "nyx_api": ">=1.0 <2.0",
        "kinds": [kind],
        "license": {"type": "free", "spdx": "MIT"},
    }
    files: dict[str, object] = {MANIFEST_NAME: manifest, **EXAMPLES[kind]}
    for rel, content in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            content
            if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        )
        with open(path, "x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(f"Creada en {folder}. Cámbiala y comprueba con: validate {folder}")


def validate(folder: Path) -> bool:
    try:
        manifest = load_manifest((folder / MANIFEST_NAME).read_bytes())
    except (OSError, ManifestError) as e:
        print(f"Manifiesto: {e}")
        return False
    content = load_content(manifest, folder)
    for problem in content.problems:
        print(f"Problema: {problem}")
    if not content.problems:
        print(f"Bien: {manifest.id} {manifest.version} ({', '.join(manifest.kinds)})")
    return not content.problems


def pack(folder: Path, out: Path | None) -> None:
    if not validate(folder):
        sys.exit("No se empaqueta: arregla lo de arriba")
    manifest = load_manifest((folder / MANIFEST_NAME).read_bytes())
    out = out or folder.parent / f"{manifest.id}-{manifest.version}.nyxext"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            if path.is_file() and not SKIP.intersection(rel.parts) and rel.name != "signature":
                zf.write(path, rel.as_posix())
    try:
        read_package(out)  # las mismas comprobaciones que al instalar
    except PackageError as e:
        out.unlink()
        sys.exit(f"El paquete no valdría: {e}")
    print(f"Empaquetada en {out} (sin firmar: para instalarla sin firma, modo desarrollador)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new")
    p_new.add_argument("carpeta", type=Path)
    p_new.add_argument("--id", required=True, help="autor.nombre (minúsculas)")
    p_new.add_argument("--tipo", choices=sorted(EXAMPLES), default="knowledge")
    sub.add_parser("validate").add_argument("carpeta", type=Path)
    p_pack = sub.add_parser("pack")
    p_pack.add_argument("carpeta", type=Path)
    p_pack.add_argument("-o", "--salida", type=Path)
    args = parser.parse_args()
    if args.cmd == "new":
        new(args.carpeta, args.id, args.tipo)
    elif args.cmd == "validate":
        sys.exit(0 if validate(args.carpeta) else 1)
    else:
        pack(args.carpeta, args.salida)


if __name__ == "__main__":
    main()
