r"""Graba fondos para la batería de audio (plan «Cerebro 2», C0) mientras juegas o escuchas música.

Graba a la vez, en %LOCALAPPDATA%\Nyx\training\bateria-audio\fondos\:

- `micro-<nombre>.wav`: el micrófono de Nyx tal cual (con cascos: tu voz hablando con otros,
  teclado, ratón y lo que se escape de los cascos). En la batería se mezcla tal cual.
- `salida-<nombre>.wav`: lo que suena por la salida de audio (sin micro): el juego o la música.
  En la batería se mezcla más bajo que la voz para simular altavoces.

    uv run python scripts/record_background.py rocket --minutos 4
    uv run python scripts/record_background.py valorant
    uv run python scripts/record_background.py fortnite
    uv run python scripts/record_background.py musica --solo-salida   # Spotify (canciones con voz)
    uv run python scripts/record_background.py discord --solo-micro   # hablando con amigos
    uv run python scripts/record_background.py --dispositivos         # ver salidas de audio

Para cuando quieras con Ctrl+C (lo grabado se guarda). No hace falta cerrar Nyx, pero **no
digas «Nyx»** mientras graba: el fondo tiene que ser lo que no va para ella.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_samples import Recorder

from nyx.audio.capture import SAMPLE_RATE
from nyx.bench.audio import level_db, resample, to_int16, write_wav
from nyx.paths import local_dir
from nyx.settings.model import load_settings

FOLDER = local_dir() / "training" / "bateria-audio" / "fondos"
LOOP_RATE = 48_000


class LoopbackRecorder:
    """Lo que suena por una salida de audio (WASAPI loopback, con `soundcard`, BSD-3)."""

    def __init__(self, device: str | None) -> None:
        import soundcard as sc  # type: ignore[import-untyped]

        speaker = sc.default_speaker()
        if device:
            matches = [s for s in sc.all_speakers() if device.lower() in s.name.lower()]
            if not matches:
                raise SystemExit(f"No encuentro la salida «{device}» (usa --dispositivos)")
            speaker = matches[0]
        self.name = speaker.name
        self._mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        self._chunks: list[np.ndarray] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="loopback", daemon=True)

    def _run(self) -> None:
        with self._mic.recorder(samplerate=LOOP_RATE, channels=2) as rec:
            while not self._stop.is_set():
                self._chunks.append(rec.record(numframes=LOOP_RATE // 10))

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> np.ndarray:
        self._stop.set()
        self._thread.join(timeout=3)
        if not self._chunks:
            return np.zeros(0, dtype=np.int16)
        stereo = np.concatenate(self._chunks)
        return to_int16(resample(stereo.mean(axis=1), LOOP_RATE, SAMPLE_RATE))


def list_outputs() -> None:
    import soundcard as sc

    default = sc.default_speaker().name
    for s in sc.all_speakers():
        print(("* " if s.name == default else "  ") + s.name)
    print("(* = la predeterminada, la que se usa si no dices --salida)")


async def record(name: str, minutes: float, *, mic: bool, out: bool, device: str | None) -> None:
    FOLDER.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    loop = LoopbackRecorder(device) if out else None
    print(f"Grabando «{name}» hasta {minutes:g} min (Ctrl+C para parar antes).")
    if mic:
        print(f"  micro: {settings.audio.input_device or 'predeterminado'}")
    if loop is not None:
        print(f"  salida: {loop.name}")
    t0 = time.monotonic()
    frames: list[np.ndarray] = []
    try:
        if loop is not None:
            loop.start()
        if mic:
            async with Recorder(settings.audio.input_device) as rec:
                rec.sink = frames
                while time.monotonic() - t0 < minutes * 60:
                    await asyncio.sleep(1)
                    left = minutes * 60 - (time.monotonic() - t0)
                    print(f"\r  {int(time.monotonic() - t0)} s (quedan {int(left)} s)  ", end="")
                rec.sink = None
        else:
            while time.monotonic() - t0 < minutes * 60:
                await asyncio.sleep(1)
                print(f"\r  {int(time.monotonic() - t0)} s  ", end="")
    except asyncio.CancelledError, KeyboardInterrupt:
        pass
    finally:
        print()
        if mic and frames:
            audio = np.concatenate(frames).astype(np.int16)
            path = FOLDER / f"micro-{name}.wav"
            write_wav(path, audio)
            print(
                f"  {path.name}: {audio.size / SAMPLE_RATE:.0f} s, nivel {level_db(audio):.0f} dBFS"
            )
        if loop is not None:
            audio = loop.stop()
            path = FOLDER / f"salida-{name}.wav"
            write_wav(path, audio)
            print(
                f"  {path.name}: {audio.size / SAMPLE_RATE:.0f} s, nivel {level_db(audio):.0f} dBFS"
            )
            if level_db(audio) < -60:
                print(
                    "  ⚠ la salida está casi en silencio: ¿sonaba por otra salida? (--dispositivos)"
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("nombre", nargs="?", help="rocket, valorant, fortnite, musica, discord…")
    parser.add_argument("--minutos", type=float, default=4.0)
    parser.add_argument("--solo-micro", action="store_true")
    parser.add_argument("--solo-salida", action="store_true")
    parser.add_argument("--salida", help="parte del nombre de la salida de audio a grabar")
    parser.add_argument("--dispositivos", action="store_true", help="ver las salidas de audio")
    args = parser.parse_args()
    if args.dispositivos:
        list_outputs()
        return 0
    if not args.nombre:
        parser.error("falta el nombre del fondo (p. ej. rocket)")
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in args.nombre.lower())
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            record(
                name,
                args.minutos,
                mic=not args.solo_salida,
                out=not args.solo_micro,
                device=args.salida,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
