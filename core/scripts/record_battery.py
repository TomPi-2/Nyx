r"""Graba la batería de audio: las frases de `tests/battery/audio/guion.jsonl`.

Todo se queda en este equipo: %LOCALAPPDATA%\Nyx\training\bateria-audio\ (es tu voz: nunca va
a git). Usa el micrófono de los ajustes de Nyx.

**Cierra Nyx antes** (bandeja → Salir): si está abierto, te oiría decir «Nyx, apaga el
ordenador» y lo haría de verdad. La grabadora no empieza con Nyx abierto.

    uv run python scripts/record_battery.py            # sigue por donde lo dejaste
    uv run python scripts/record_battery.py --tanda 50 # para tras 50 frases (por defecto)
    uv run python scripts/record_battery.py --repetir pau003   # vuelve a grabar una
    uv run python scripts/record_battery.py --estado   # cuántas hay grabadas por tipo

Cómo va cada frase:
  1. Lee la frase y cómo decirla. Pulsa Enter y empieza a hablar cuando veas «● Grabando».
  2. Al terminar de hablar, espera un momento y pulsa Enter otra vez.
     En las que se dejan «a medias», espera unos 3 s en silencio antes de pulsar Enter.
Teclas (escribe la letra y Enter en vez de solo Enter): e = escuchar la última,
r = repetir la última, s = saltar esta, q = salir (lo grabado se queda).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_samples import Recorder

from nyx.audio.capture import FRAME_S, SAMPLE_RATE
from nyx.bench.audio import frame_db, level_db, write_wav
from nyx.bench.guion import Item, load
from nyx.paths import local_dir
from nyx.settings.model import load_settings

FOLDER = local_dir() / "training" / "bateria-audio"
LEAD_S = 0.5  # audio de antes de pulsar Enter (por si se empieza a hablar enseguida)
TAIL_S = 0.3  # y de después de la segunda pulsación
ORDER_SEED = 2026  # orden fijo pero mezclado: cada tanda tiene de todo


def nyx_running() -> list[int]:
    """PIDs del núcleo de Nyx abierto (instalado o en desarrollo)."""
    found = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        name = (proc.info.get("name") or "").lower()
        cmd = " ".join(proc.info.get("cmdline") or [])
        if (name == "python.exe" and (" -m nyx" in cmd or "\\nyx.exe" in cmd)) or name == "nyx.exe":
            found.append(proc.pid)
    return found


def order(items: list[Item]) -> list[Item]:
    """Mezcladas con semilla fija, pero las de un grupo juntas y en su orden."""
    groups: dict[str, list[Item]] = {}
    units: list[list[Item]] = []
    for it in items:
        if it.grupo is None:
            units.append([it])
        elif it.grupo in groups:
            groups[it.grupo].append(it)
        else:
            groups[it.grupo] = [it]
            units.append(groups[it.grupo])
    random.Random(ORDER_SEED).shuffle(units)
    return [it for unit in units for it in unit]


def done_ids() -> set[str]:
    return {p.stem for p in FOLDER.glob("*.wav")}


def status(items: list[Item]) -> None:
    done = done_ids()
    total = Counter(i.categoria for i in items)
    have = Counter(i.categoria for i in items if i.id in done)
    print(f"Grabadas {len(done & {i.id for i in items})} de {len(items)} en {FOLDER}")
    for cat, n in sorted(total.items()):
        print(f"  {cat:12} {have[cat]:3}/{n}")


def check_level(audio: np.ndarray) -> str:
    """Aviso si la grabación salió muy baja, saturada o sin voz."""
    peak = float(np.abs(audio.astype(np.int32)).max(initial=0)) / 32768.0
    if peak >= 0.99:
        return "⚠ saturada: aléjate un poco del micro o baja su ganancia"
    if (frame_db(audio) > -45).sum() < 3:
        return "⚠ casi no se oye nada: ¿micro silenciado?"
    if level_db(audio, active_only=True) < -38:
        return "⚠ muy baja: acércate al micro"
    return ""


async def ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip().lower()


async def play(audio: np.ndarray) -> None:
    import sounddevice as sd

    settings = load_settings()
    from nyx.audio import devices

    index, _ = devices.resolve("output", settings.audio.output_device)
    await asyncio.to_thread(sd.play, audio, SAMPLE_RATE, device=index, blocking=True)


async def record_one(rec: Recorder, item: Item, pos: str) -> tuple[str, np.ndarray | None]:
    """Graba una frase. Devuelve (orden, audio): orden = «ok», «r», «s», «q» o «e»."""
    who = "" if item.nyx else "   (sin «Nyx»)"
    print()
    print(f"{pos}  [{item.categoria}]{who}")
    print(f"   «{item.frase}»")
    if item.como:
        print(f"   → {item.como}")
    answer = await ask("   Enter para grabar (e/r/s/q): ")
    if answer in {"e", "r", "s", "q"}:
        return answer, None
    rec.sink = list(rec.recent)[-int(LEAD_S / FRAME_S) :]
    print("   ● Grabando… (Enter al terminar)", flush=True)
    await ask("")
    await asyncio.sleep(TAIL_S)
    frames, rec.sink = rec.sink or [], None
    return "ok", np.concatenate(frames).astype(np.int16)


async def session(items: list[Item], todo: list[Item], batch: int) -> None:
    settings = load_settings()
    mic = settings.audio.input_device or "el micro predeterminado"
    print(f"Micro: {mic}. Carpeta: {FOLDER}")
    FOLDER.mkdir(parents=True, exist_ok=True)
    meta = FOLDER / "grabaciones.jsonl"
    last: tuple[Item, np.ndarray] | None = None
    async with Recorder(settings.audio.input_device, keep_s=3.0) as rec:
        i = 0
        recorded = 0
        while i < len(todo) and recorded < batch:
            item = todo[i]
            pos = f"[{len(done_ids()) + 1}/{len(items)}]"
            action, audio = await record_one(rec, item, pos)
            if action == "q":
                break
            if action == "s":
                i += 1
                continue
            if action == "e":
                if last is not None:
                    await play(last[1])
                continue
            if action == "r":
                if last is not None:
                    # Repetir la anterior: se vuelve a ella.
                    todo.insert(i, last[0])
                    print(f"   Repetimos {last[0].id}.")
                continue
            assert audio is not None
            if warning := check_level(audio):
                print(f"   {warning}")
                again = await ask("   ¿La repites? (Enter = sí, n = guardarla así): ")
                if again != "n":
                    continue
            write_wav(FOLDER / f"{item.id}.wav", audio)
            with meta.open("a", encoding="utf-8") as f:
                entry = {
                    "id": item.id,
                    "fecha": datetime.now().isoformat(timespec="seconds"),
                    "micro": mic,
                    "segundos": round(audio.size / SAMPLE_RATE, 2),
                    "nivel_db": round(level_db(audio, active_only=True), 1),
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            last = (item, audio)
            recorded += 1
            i += 1
    print()
    print(f"Esta tanda: {recorded} frases.")
    status(items)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--tanda", type=int, default=50, help="frases por tanda (por defecto 50)")
    parser.add_argument("--repetir", nargs="+", metavar="ID", help="volver a grabar estas")
    parser.add_argument("--estado", action="store_true", help="solo decir cuántas hay")
    parser.add_argument(
        "--con-nyx-abierto",
        action="store_true",
        help="grabar aunque Nyx esté abierto (no recomendado: puede hacer lo que oye)",
    )
    args = parser.parse_args()
    items = load()
    if args.estado:
        status(items)
        return 0
    if (pids := nyx_running()) and not args.con_nyx_abierto:
        print(
            "Nyx está abierto (núcleo: " + ", ".join(map(str, pids)) + "). Ciérralo antes "
            "(bandeja → Salir): si no, haría lo que oye («apaga el ordenador»…)."
        )
        return 1
    by_id = {i.id: i for i in items}
    if args.repetir:
        missing = [x for x in args.repetir if x not in by_id]
        if missing:
            print("No existen: " + ", ".join(missing))
            return 1
        todo = [by_id[x] for x in args.repetir]
        batch = len(todo)
    else:
        done = done_ids()
        todo = [i for i in order(items) if i.id not in done]
        batch = args.tanda
        if not todo:
            print("Ya están todas grabadas.")
            status(items)
            return 0
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(session(items, todo, batch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
