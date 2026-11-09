import time

import numpy as np
import pytest

from nyx.tts.pocket import PocketTTS, cache_dir


def downloaded() -> bool:
    return any(cache_dir().glob("models--kyutai--*"))


@pytest.mark.skipif(not downloaded(), reason="voz lola no descargada")
async def test_real_lola_streams_quickly() -> None:
    tts = PocketTTS("lola")
    await tts.load()
    t0 = time.perf_counter()
    first = None
    chunks = []
    async for chunk in tts.stream("Vale, he movido los dos archivos a Documentos."):
        first = first if first is not None else time.perf_counter() - t0
        chunks.append(chunk)
    audio = np.concatenate(chunks)
    assert tts.sample_rate == 24_000
    assert 1.0 < audio.size / tts.sample_rate < 6.0
    assert float(np.abs(audio).max()) > 0.05
    assert first is not None and first < 1.0  # en el PC de referencia ~0,08 s


async def test_stream_can_be_abandoned_midway() -> None:
    if not downloaded():
        pytest.skip("voz lola no descargada")
    tts = PocketTTS("lola")
    await tts.load()
    stream = tts.stream("Un agujero negro es una región del espacio donde la gravedad es enorme.")
    async for _ in stream:
        break
    await stream.aclose()  # se para la generación y se libera el modelo
    audio = await tts.synthesize("Hola.")
    assert audio.size > 0
