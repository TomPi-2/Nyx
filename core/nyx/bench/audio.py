"""Audio de la batería: WAV de 16 kHz mono, cambio de frecuencia y mezcla con fondos.

Las frases se graban en silencio y los fondos aparte; aquí se mezclan a un volumen dado para
probar cada frase en varias situaciones sin grabarla otra vez.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

from nyx.audio.capture import FRAME_SAMPLES, SAMPLE_RATE

Audio = npt.NDArray[np.int16]

# Por encima de este nivel (dBFS) un bloque cuenta como voz al medir el volumen de una frase:
# así el silencio de antes y de después no baja la medida.
ACTIVE_DB = -45.0


def read_wav(path: Path) -> Audio:
    """WAV en int16 a 16 kHz mono (los de la batería ya lo son; si no, se convierte)."""
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{path.name}: solo WAV de 16 bits")
    data = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1).astype(np.int16)
    if rate != SAMPLE_RATE:
        data = to_int16(resample(data.astype(np.float32) / 32768.0, rate, SAMPLE_RATE))
    return data


def write_wav(path: Path, audio: Audio, rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(audio, dtype=np.int16).tobytes())


def to_int16(x: npt.NDArray[np.floating]) -> Audio:
    """Float en [-1, 1] → int16, recortando lo que se salga."""
    return np.clip(np.round(x * 32767.0), -32768, 32767).astype(np.int16)


def resample(x: npt.NDArray[np.floating], src: int, dst: int) -> npt.NDArray[np.float32]:
    """Cambio de frecuencia con un filtro paso bajo (sinc con ventana) e interpolación.

    Suficiente para pasar el sonido de un juego de 48 kHz a 16 kHz: lo que importa es que no
    entren frecuencias por encima de 8 kHz disfrazadas de otras (aliasing)."""
    x = np.asarray(x, dtype=np.float32)
    if src == dst or x.size == 0:
        return x
    if dst < src:
        cutoff = 0.45 * dst / src  # un poco por debajo de la mitad de la frecuencia nueva
        taps = 129
        t = np.arange(taps) - (taps - 1) / 2
        kernel = 2 * cutoff * np.sinc(2 * cutoff * t) * np.hamming(taps)
        x = np.convolve(x, (kernel / kernel.sum()).astype(np.float32), mode="same")
    n_out = round(x.size * dst / src)
    positions = np.arange(n_out) * (src / dst)
    out: npt.NDArray[np.float32] = np.interp(positions, np.arange(x.size), x).astype(np.float32)
    return out


def frame_db(audio: Audio) -> npt.NDArray[np.float64]:
    """Nivel (dBFS) de cada bloque de 32 ms."""
    n = audio.size // FRAME_SAMPLES
    if n == 0:
        return np.zeros(0)
    blocks = audio[: n * FRAME_SAMPLES].astype(np.float64).reshape(n, FRAME_SAMPLES) / 32768.0
    rms = np.sqrt(np.mean(np.square(blocks), axis=1))
    return np.asarray(20.0 * np.log10(rms + 1e-9))


def level_db(audio: Audio, *, active_only: bool = False) -> float:
    """Nivel medio (dBFS); con `active_only`, solo de los bloques con sonido."""
    if audio.size == 0:
        return -120.0
    if active_only:
        db = frame_db(audio)
        loud = db[db > ACTIVE_DB]
        if loud.size:
            # Media de la energía, no de los dB.
            return float(10.0 * np.log10(np.mean(np.power(10.0, loud / 10.0))))
    rms = math.sqrt(float(np.mean(np.square(audio.astype(np.float64) / 32768.0))))
    return 20.0 * math.log10(rms + 1e-9)


def loop_to(background: Audio, length: int, offset: int = 0) -> Audio:
    """El fondo repetido o recortado hasta `length` muestras, empezando en `offset`."""
    if background.size == 0:
        return np.zeros(length, dtype=np.int16)
    start = offset % background.size
    reps = math.ceil((start + length) / background.size)
    return np.tile(background, reps)[start : start + length]


def mix(
    speech: Audio,
    background: Audio,
    *,
    snr_db: float | None = None,
    gain_db: float = 0.0,
    offset: int = 0,
) -> Audio:
    """La frase con el fondo debajo.

    - `snr_db`: el fondo queda `snr_db` dB por debajo de la voz (medida solo donde hay voz).
      Es la forma de simular altavoces con el sonido grabado de la salida de audio.
    - Sin `snr_db`: el fondo va tal cual se grabó (más `gain_db`). Es lo realista con un fondo
      grabado por el propio micro (cascos, Discord, teclado).
    """
    bg = loop_to(background, speech.size, offset).astype(np.float64)
    if snr_db is not None:
        target = level_db(speech, active_only=True) - snr_db
        current = level_db(background)
        gain = 10.0 ** ((target - current) / 20.0)
    else:
        gain = 10.0 ** (gain_db / 20.0)
    total = speech.astype(np.float64) + gain * bg
    out: Audio = np.clip(np.round(total), -32768, 32767).astype(np.int16)
    return out


def voiced_span(audio: Audio, *, threshold_db: float = ACTIVE_DB) -> tuple[float, float] | None:
    """(inicio, fin) en segundos de lo que suena por encima del umbral, o None si nada.

    Con la grabación limpia sirve para saber cuándo acabó de hablar el usuario de verdad y
    medir cuánto tardó Nyx en darse cuenta (o si le cortó antes)."""
    db = frame_db(audio)
    loud = np.flatnonzero(db > threshold_db)
    if loud.size == 0:
        return None
    frame_s = FRAME_SAMPLES / SAMPLE_RATE
    return float(loud[0] * frame_s), float((loud[-1] + 1) * frame_s)
