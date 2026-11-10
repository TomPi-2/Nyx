"""Rasgos de audio: el cálculo al vuelo (Nyx) debe dar lo mismo que por clips (entrenamiento).

Necesita los modelos de rasgos descargados (training/download.py --solo oww); si no, se salta.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from nyx.wake.features import EMB_DIM, N_EMB, FeatureExtractor, StreamingFeatures

OWW = Path(os.environ.get("LOCALAPPDATA", "")) / "Nyx" / "training" / "datos" / "oww"
pytestmark = pytest.mark.skipif(
    not (OWW / "embedding_model.onnx").exists(), reason="modelos de rasgos sin descargar"
)


@pytest.fixture(scope="module")
def extractor() -> FeatureExtractor:
    return FeatureExtractor(OWW / "melspectrogram.onnx", OWW / "embedding_model.onnx")


def test_streaming_matches_clip(extractor: FeatureExtractor) -> None:
    rng = np.random.default_rng(1)
    audio = (rng.standard_normal(16000 * 3) * 2000).astype(np.int16)
    batch = extractor.clip(audio)
    stream = StreamingFeatures(extractor)
    got = []
    for i in range(0, len(audio), 512):  # bloques de 32 ms, como el micro
        added = stream.feed(audio[i : i + 512])
        if added:  # un bloque puede completar más de un vector
            got += list(stream.embeddings)[-added:]
    got_arr = np.stack(got)
    assert batch.shape[1] == EMB_DIM
    n = min(len(batch), len(got_arr))
    assert n >= len(batch) - 1
    np.testing.assert_allclose(got_arr[:n], batch[:n], rtol=1e-3, atol=1e-3)


def test_window_needs_enough_audio(extractor: FeatureExtractor) -> None:
    stream = StreamingFeatures(extractor)
    stream.feed(np.zeros(16000, dtype=np.int16))
    assert stream.window() is None
    stream.feed(np.zeros(16000, dtype=np.int16))
    window = stream.window()
    assert window is not None and window.shape == (N_EMB, EMB_DIM)


def test_sensitivity_maps_to_threshold() -> None:
    from nyx.wake.own_engine import threshold_for

    assert threshold_for(1) == 0.9 and threshold_for(10) == 0.18
    assert threshold_for(6) == 0.5
    assert threshold_for(0) == 0.9 and threshold_for(99) == 0.18  # fuera de rango
    assert [threshold_for(i) for i in range(1, 11)] == sorted(
        (threshold_for(i) for i in range(1, 11)), reverse=True
    )
