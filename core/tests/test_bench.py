"""Banco de pruebas del plan «Cerebro 2» (C0): audio, métricas, guion, recursos y arnés."""

from __future__ import annotations

import numpy as np
import pytest

from nyx.audio.capture import FRAME_SAMPLES, SAMPLE_RATE
from nyx.bench.audio import level_db, loop_to, mix, resample, voiced_span
from nyx.bench.guion import CATEGORIAS, Item, load
from nyx.bench.harness import Bench, BenchCapture, DryExecutor, SilentTTS, TimedSTT
from nyx.bench.metrics import Observed, Verdict, judge, percentile, wer
from nyx.bench.resmon import gpu_by_pid, vram_by_pid
from nyx.settings.model import Settings
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry
from tests.test_pipeline import SILENCE, SPEECH, WAKE, Harness, frame, n

# --- audio ---


def tone(seconds: float, amplitude: float, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amplitude * 32767 * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def test_mix_puts_background_at_the_asked_snr() -> None:
    speech = np.concatenate([np.zeros(SAMPLE_RATE, np.int16), tone(1.0, 0.3)])
    noise = (np.random.default_rng(1).normal(0, 3000, SAMPLE_RATE // 2)).astype(np.int16)
    mixed = mix(speech, noise, snr_db=10.0)
    assert mixed.size == speech.size
    added = mixed.astype(np.int32) - speech.astype(np.int32)
    # El fondo queda 10 dB por debajo de la voz (medida solo donde hay voz).
    gap = level_db(speech, active_only=True) - level_db(added.astype(np.int16))
    assert gap == pytest.approx(10.0, abs=0.5)


def test_mix_without_snr_keeps_background_as_recorded() -> None:
    speech = np.zeros(1000, np.int16)
    noise = np.full(300, 100, np.int16)
    assert np.array_equal(mix(speech, noise), loop_to(noise, 1000))


def test_mix_clips_instead_of_wrapping_around() -> None:
    loud = np.full(100, 30000, np.int16)
    assert int(mix(loud, loud).max()) == 32767


def test_loop_to_repeats_and_offsets() -> None:
    bg = np.arange(5, dtype=np.int16)
    assert loop_to(bg, 7, offset=3).tolist() == [3, 4, 0, 1, 2, 3, 4]


def test_resample_48k_to_16k_keeps_length_and_low_tones() -> None:
    t = np.arange(48_000) / 48_000
    x = 0.5 * np.sin(2 * np.pi * 300 * t)
    y = resample(x, 48_000, 16_000)
    assert y.size == 16_000
    assert float(np.abs(y[1000:-1000]).max()) == pytest.approx(0.5, abs=0.05)


def test_resample_removes_tones_above_the_new_nyquist() -> None:
    t = np.arange(48_000) / 48_000
    y = resample(0.5 * np.sin(2 * np.pi * 12_000 * t), 48_000, 16_000)
    assert float(np.abs(y[1000:-1000]).max()) < 0.05  # sin aliasing


def test_voiced_span_finds_where_speech_ends() -> None:
    audio = np.concatenate(
        [np.zeros(SAMPLE_RATE, np.int16), tone(0.5, 0.3), np.zeros(8000, np.int16)]
    )
    span = voiced_span(audio)
    assert span is not None
    assert span[0] == pytest.approx(1.0, abs=0.04)
    assert span[1] == pytest.approx(1.5, abs=0.04)
    assert voiced_span(np.zeros(4000, np.int16)) is None


# --- métricas ---


def test_wer_ignores_wake_word_accents_and_punctuation() -> None:
    assert wer("Nyx, ábreme el Fortnite", "Nix. Abreme el fortnite.") == (0, 3)
    assert wer("abre el discord", "abre el dis cord") == (2, 3)


def test_percentile_interpolates() -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 95) == 5


def seen(calls: list[tuple[str, dict[str, object]]] | None = None, reply: str = "") -> Observed:
    return Observed(True, list(calls or []), reply)


def test_judge_action() -> None:
    expected = {"tool": "open_app", "args": {"name": "Spotify"}}
    assert judge(expected, seen([("open_app", {"name": "Spotify"})])) is Verdict.BIEN
    assert judge(expected, seen([("open_app", {"name": "Steam"})])) is Verdict.MAL
    assert judge(expected, seen(reply="¿Spotify o Steam?")) is Verdict.PREGUNTO
    assert judge(expected, seen(reply="No encuentro eso.")) is Verdict.NADA
    assert judge(expected, Observed(False, [], "")) is Verdict.NO_ACTIVO


def test_judge_plan_and_waits() -> None:
    expected = {"plan": ["open_app", "type_text"]}
    calls = [("open_app", {}), ("wait_for_window", {}), ("type_text", {})]
    assert judge(expected, seen(calls)) is Verdict.BIEN
    assert judge(expected, seen([("open_app", {})])) is Verdict.MAL


def test_judge_types() -> None:
    assert judge({"tipo": "preguntar"}, seen(reply="¿Qué carpeta?")) is Verdict.PREGUNTO
    assert judge({"tipo": "preguntar"}, seen(reply="No encuentro de.")) is Verdict.NADA
    assert judge({"tipo": "preguntar"}, seen([("open_path", {})])) is Verdict.MAL
    assert judge({"tipo": "respuesta"}, seen(reply="Son las tres.")) is Verdict.BIEN
    assert judge({"tipo": "respuesta"}, seen(reply="Aún no sé hacer eso.")) is Verdict.NADA
    # No era para Nyx: lo bueno es no hacer nada (aunque no se active).
    assert judge({"tipo": "ignorar"}, Observed(False, [], "")) is Verdict.BIEN
    assert judge({"tipo": "ignorar"}, seen(reply="¡Hola!")) is Verdict.SIN_DEBER


# --- guion ---


def test_guion_is_valid_and_uses_real_tools() -> None:
    items = load()
    assert len(items) >= 350
    registry = default_registry()
    for item in items:
        names = [*(item.tool or "").split("|"), *[p for s in item.plan or [] for p in s.split("|")]]
        for name in filter(None, names):
            assert registry.get(name) is not None, f"{item.id}: {name} no existe"
    assert {i.categoria for i in items} == set(CATEGORIAS)


def test_guion_groups_are_together_and_start_with_nyx() -> None:
    items = load()
    seen_groups: set[str] = set()
    previous: str | None = None
    for item in items:
        if item.grupo and item.grupo != previous:
            assert item.grupo not in seen_groups, f"grupo {item.grupo} partido"
            assert item.nyx, f"{item.id}: la primera de un grupo lleva «Nyx»"
            seen_groups.add(item.grupo)
        previous = item.grupo


def test_item_needs_exactly_one_expectation() -> None:
    with pytest.raises(ValueError):
        Item(id="x", categoria="orden", frase="Nyx")
    with pytest.raises(ValueError):
        Item(id="x", categoria="orden", frase="Nyx", tool="undo", tipo="respuesta")


# --- recursos ---


def test_gpu_by_pid_like_task_manager() -> None:
    engines = {
        "pid_10_luid_0x0_phys_0_eng_0_engtype_3D": 30.0,
        "pid_10_luid_0x0_phys_0_eng_1_engtype_3D": 10.0,
        "pid_10_luid_0x0_phys_0_eng_2_engtype_Compute": 25.0,
        "pid_20_luid_0x0_phys_0_eng_0_engtype_Compute": 50.0,
        "basura": 99.0,
    }
    by_pid, total = gpu_by_pid(engines)
    assert by_pid == {10: 40.0, 20: 50.0}  # por proceso: el tipo de motor más alto
    assert total == 75.0  # Compute: 25 + 50


def test_vram_by_pid_in_mb() -> None:
    memory = {"pid_7_luid_0x0_phys_0": 2 * 1024 * 1024 * 1024, "pid_7_luid_0x1_phys_0": 0.0}
    assert vram_by_pid(memory) == {7: 2048.0}


# --- arnés ---


async def test_dry_executor_never_runs_tools() -> None:
    registry = default_registry()
    dry = DryExecutor(registry, ToolContext(index=None, settings=Settings()))  # type: ignore[arg-type]
    from nyx.executor import ToolCall

    result = await dry.run(ToolCall("system_power", {"action": "shutdown"}))
    assert result.ok
    assert [(n, a) for _, n, a in dry.calls] == [("system_power", {"action": "shutdown"})]
    bad = await dry.run(ToolCall("no_existe", {}))
    assert not bad.ok
    assert len(dry.calls) == 1


async def test_bench_runs_a_phrase_through_the_pipeline() -> None:
    h = Harness()
    capture = BenchCapture()
    tts = SilentTTS()
    stt = TimedSTT(h.stt)
    h.p.capture = capture  # type: ignore[assignment]
    h.p.tts = tts  # type: ignore[assignment]
    h.p.stt = stt  # type: ignore[assignment]
    dry = DryExecutor(default_registry(), ToolContext(index=None, settings=Settings()))  # type: ignore[arg-type]
    bench = Bench(h.p, capture=capture, executor=dry, tts=tts, stt=stt, realtime=False)
    clip = np.concatenate(
        [frame(WAKE), *[frame(SPEECH)] * n(1.0), *[frame(SILENCE)] * n(0.2)]
    ).astype(np.int16)

    def silence(size: int) -> np.ndarray:
        return np.zeros(size, np.int16)

    trace = await bench.run(clip, silence, speech_end_s=(1 + n(1.0)) * FRAME_SAMPLES / SAMPLE_RATE)
    assert trace.activated
    assert trace.transcript == "¿Cómo se dice hola en alemán?"
    assert trace.reply == "En alemán se dice Hallo."
    assert trace.calls == []
    assert trace.stt_calls  # contó las transcripciones
    assert trace.listen_end is not None and trace.speech_end is not None
    bench.close()
    await h.p.close()
