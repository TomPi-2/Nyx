import io
import wave

import numpy as np

from nyx.stt.whisper_server import VulkanDevice, parse_devices, pick_device, to_wav

# Registro real de whisper-server en el PC de referencia (docs/benchmarks).
LOG = [
    "ggml_vulkan: Found 2 Vulkan devices:",
    "ggml_vulkan: 0 = AMD Radeon RX 7700 XT (AMD proprietary driver) | uma: 0 | fp16: 1 | bf16: 1"
    " | fp4: 0 | warp size: 64 | shared memory: 32768 | int dot: 1 | matrix cores: KHR_coopmat",
    "ggml_vulkan: 1 = AMD Radeon(TM) Graphics (AMD proprietary driver) | uma: 1 | fp16: 1"
    " | bf16: 0 | fp4: 0 | warp size: 32 | shared memory: 32768 | int dot: 1 | matrix cores: none",
    "whisper_init_with_params_no_state: gpu_device = 0",
]

IGPU_FIRST = [
    "ggml_vulkan: 0 = AMD Radeon(TM) Graphics (AMD proprietary driver) | uma: 1 | fp16: 1",
    "ggml_vulkan: 1 = NVIDIA GeForce RTX 3070 Laptop GPU (NVIDIA) | uma: 0 | fp16: 1",
]


def test_parse_devices() -> None:
    assert parse_devices(LOG) == [
        VulkanDevice(0, "AMD Radeon RX 7700 XT", integrated=False),
        VulkanDevice(1, "AMD Radeon(TM) Graphics", integrated=True),
    ]


def test_prefers_dedicated_gpu_even_if_listed_second() -> None:
    chosen = pick_device(parse_devices(IGPU_FIRST), None)
    assert chosen is not None and chosen.index == 1 and "RTX" in chosen.name


def test_preferred_name_wins() -> None:
    chosen = pick_device(parse_devices(LOG), "radeon(tm)")
    assert chosen is not None and chosen.index == 1


def test_unknown_preference_falls_back_to_dedicated() -> None:
    chosen = pick_device(parse_devices(LOG), "Intel Arc")
    assert chosen is not None and chosen.index == 0


def test_no_devices() -> None:
    assert pick_device([], None) is None


def test_to_wav_roundtrip() -> None:
    pcm = (np.arange(1600) % 100).astype(np.int16)
    with wave.open(io.BytesIO(to_wav(pcm))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert np.array_equal(np.frombuffer(w.readframes(1600), dtype=np.int16), pcm)
