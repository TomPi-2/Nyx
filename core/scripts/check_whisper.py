"""Prueba técnica de la fase 1: whisper.cpp con Vulkan.

Arranca whisper-server con el modelo cargado (como hará Nyx: proceso residente) y mide
la latencia de transcribir frases cortas en español.

Uso (desde core/):
  uv run python scripts/check_whisper.py --server <ruta>/whisper-server.exe \
      --model <ruta>/ggml-large-v3-turbo-q5_0.bin [--audio frase.wav ...]

Sin --audio, genera frases de prueba con la voz española de Windows (SAPI).
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from hwinfo import hardware, save_report

PHRASES = [
    "Nyx, abre Visual Studio Code.",
    "Pon una alarma a las diez y cincuenta.",
    "Mueve los últimos cinco archivos de Descargas a Documentos.",
]


def synthesize(text: str, out: Path) -> None:
    """WAV de 16 kHz mono con la voz española de Windows, si está instalada."""
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es-*' }"
        " | Select-Object -First 1;"
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
        " [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
        " [System.Speech.AudioFormat.AudioChannel]::Mono);"
        f"$s.SetOutputToWaveFile('{out}', $f); $s.Speak('{text}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=60)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", type=Path, required=True, help="whisper-server.exe")
    parser.add_argument("--model", type=Path, required=True, help="modelo ggml (.bin)")
    parser.add_argument("--audio", type=Path, nargs="*", default=[])
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="nyx-whisper-"))
    audio: list[Path] = list(args.audio)
    if not audio:
        for i, text in enumerate(PHRASES):
            wav = tmp / f"frase{i}.wav"
            synthesize(text, wav)
            audio.append(wav)

    port = free_port()
    log_path = tmp / "server.log"
    t0 = time.perf_counter()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(
            [str(args.server), "-m", str(args.model), "-l", "es", "--port", str(port)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=120)
    try:
        while True:
            if proc.poll() is not None:
                print(log_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
                return 1
            with contextlib.suppress(httpx.HTTPError):
                client.get("/")
                break
            time.sleep(0.25)
        load_s = time.perf_counter() - t0

        results: list[dict[str, Any]] = []
        for wav in audio:
            times, text = [], ""
            for _ in range(args.runs):
                t = time.perf_counter()
                with wav.open("rb") as f:
                    resp = client.post(
                        "/inference",
                        files={"file": (wav.name, f, "audio/wav")},
                        data={"response_format": "json", "language": "es"},
                    )
                times.append(time.perf_counter() - t)
                text = resp.json().get("text", "").strip()
            results.append(
                {"audio": wav.name, "latency_s": round(statistics.median(times), 3), "text": text}
            )
            print(f"· {results[-1]}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    backend_lines = [
        line.strip()
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if any(k in line.lower() for k in ("vulkan", "backend", "gpu", "device"))
    ]
    report = {
        "hardware": hardware(),
        "model": args.model.name,
        "load_s": round(load_s, 2),
        "backend": backend_lines[:10],
        "results": results,
        "median_latency_s": statistics.median(r["latency_s"] for r in results),
    }
    path = save_report("whisper", report)
    print(f"Informe guardado en {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
