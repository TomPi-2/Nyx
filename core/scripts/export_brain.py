"""Prepara el cerebro de Nyx (el LoRA adoptado, `nyx-r2:7b`) para descargarlo (9.08b).

    uv run python scripts/export_brain.py                 # nyx-r2:7b → ../dist/brain
    uv run python scripts/export_brain.py --model nyx-r3:7b --tag cerebro-r3

- Toma el GGUF de dentro de Ollama (la capa del modelo: su nombre es su SHA-256) y lo parte
  en trozos de menos de 2 GB (el límite de cada archivo en una Release de GitHub).
- Escribe `nyx/brain/data/cerebro.json`: el nombre en Ollama, la huella total, cada trozo con
  su tamaño y huella, la Release donde irán, y la plantilla, el sistema y la licencia de
  Qwen2.5 (Apache-2.0) tal cual los usa Ollama: así se crea igual en cualquier equipo.
- Los trozos (`../dist/brain/`) se suben a la Release al publicar (CLAUDE.md, «antes de
  publicar»). Hasta entonces, la descarga falla y el primer arranque baja `qwen2.5:7b`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
OUT = CORE.parent / "dist" / "brain"
MANIFEST = CORE / "nyx" / "brain" / "data" / "cerebro.json"
PART = 1_900_000_000  # menos de 2 GiB por archivo en GitHub
CHUNK = 1 << 22


def modelfile(model: str) -> str:
    return subprocess.run(
        ["ollama", "show", model, "--modelfile"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def parse(text: str) -> tuple[Path, dict[str, str]]:
    """El blob de los pesos (FROM) y las órdenes con texto entre triples comillas o en línea."""
    blob = Path(re.search(r"^FROM (.+)$", text, re.M).group(1).strip())  # type: ignore[union-attr]
    fields: dict[str, str] = {}
    for key in ("TEMPLATE", "SYSTEM", "LICENSE"):
        quoted = re.search(rf'^{key} """(.*?)"""', text, re.M | re.S)
        inline = re.search(rf"^{key} (?!\"\"\")(.+)$", text, re.M)
        if quoted:
            fields[key.lower()] = quoted.group(1)
        elif inline:
            fields[key.lower()] = inline.group(1).strip()
    if re.search(r"^PARAMETER ", text, re.M):
        raise SystemExit("El modelo tiene PARAMETER: hay que añadirlos al manifiesto")
    return blob, fields


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", default="nyx-r2:7b")
    p.add_argument("--tag", default="cerebro-r2", help="Release de GitHub donde irán los trozos")
    args = p.parse_args()

    blob, fields = parse(modelfile(args.model))
    digest = blob.name.removeprefix("sha256-")
    OUT.mkdir(parents=True, exist_ok=True)
    base = args.model.replace(":", "-")
    total = hashlib.sha256()
    parts: list[dict[str, object]] = []
    remaining = blob.stat().st_size
    count = -(-remaining // PART)  # cuántos trozos, redondeando hacia arriba
    with blob.open("rb") as src:
        for index in range(1, count + 1):
            name = f"{base}.gguf.{index:03d}"
            want = min(PART, remaining)
            h = hashlib.sha256()
            size = 0
            with (OUT / name).open("wb") as dst:
                while size < want:
                    data = src.read(min(CHUNK, want - size))
                    if not data:
                        raise SystemExit("El GGUF se ha acabado antes de tiempo")
                    dst.write(data)
                    h.update(data)
                    total.update(data)
                    size += len(data)
            remaining -= size
            parts.append({"file": name, "size": size, "sha256": h.hexdigest()})
            print(f"{name}: {size / 1e9:.2f} GB")
    if total.hexdigest() != digest:
        raise SystemExit("La huella del GGUF no coincide con su nombre en Ollama")
    manifest = {
        "name": args.model,
        "release": args.tag,
        "sha256": digest,
        "size": sum(int(str(x["size"])) for x in parts),
        "parts": parts,
        **fields,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Manifiesto: {MANIFEST}")
    print(f"Trozos en {OUT}: súbelos a la Release «{args.tag}» al publicar.")


if __name__ == "__main__":
    main()
