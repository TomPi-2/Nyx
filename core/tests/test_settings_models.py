import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from nyx.brain.memory import ShortMemory
from nyx.brain.prompts import spanish_datetime
from nyx.models import DownloadError, ModelFile, download, safe_extract
from nyx.settings import Settings, load_settings, save_settings


def test_settings_created_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = load_settings(path)
    assert path.exists()
    assert s.llm.model == "qwen2.5:7b"
    assert s.listen.silence_ms == 700
    assert s.responses.tone == "cercano"


def test_settings_roundtrip_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings()
    s.tts.voice = "davefx"
    save_settings(s, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["futuro"] = {"x": 1}
    data["listen"]["silence_ms"] = 900
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.tts.voice == "davefx"
    assert loaded.listen.silence_ms == 900


def test_broken_settings_use_defaults_without_overwriting(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ roto", encoding="utf-8")
    assert load_settings(path) == Settings()
    assert path.read_text(encoding="utf-8") == "{ roto"


def test_invalid_value_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"listen": {"silence_ms": 5}}), encoding="utf-8")
    assert load_settings(path).listen.silence_ms == 700


def test_glass_defaults_and_old_files(tmp_path: Path) -> None:
    """Un settings.json anterior al motor de cristal recibe los valores predeterminados."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"appearance": {"indicator_size": 120}}), encoding="utf-8")
    glass = load_settings(path).appearance.glass
    assert (glass.quality, glass.motion, glass.edge, glass.show_in_captures) == (
        "auto",
        "siempre",
        5,
        False,
    )


def test_glass_edge_out_of_range_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    data = {"appearance": {"glass": {"edge": 12, "quality": "alto"}}}
    path.write_text(json.dumps(data), encoding="utf-8")
    # Un valor no válido invalida el archivo entero (comportamiento general de los ajustes).
    assert load_settings(path).appearance.glass.edge == 5


def _model(content: bytes, *, extract: bool = False, name: str = "m.bin") -> ModelFile:
    return ModelFile(
        key="t",
        filename=name,
        url="http://modelos/" + name,
        sha256=hashlib.sha256(content).hexdigest(),
        size_mb=1,
        license="MIT",
        extract=extract,
    )


def _client(content: bytes) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content))
    )


def test_download_verifies_hash(tmp_path: Path) -> None:
    model = _model(b"pesos")
    assert download(model, tmp_path, client=_client(b"pesos")).read_bytes() == b"pesos"
    bad = _model(b"otros", name="b.bin")
    with pytest.raises(DownloadError):
        download(bad, tmp_path, client=_client(b"manipulado"))
    assert not (tmp_path / "b.bin").exists()
    assert not (tmp_path / "b.bin.part").exists()


def test_download_extracts_zip(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("vosk-x/README", "hola")
    content = buf.getvalue()
    model = _model(content, extract=True, name="vosk-x.zip")
    final = download(model, tmp_path, client=_client(content))
    assert final == tmp_path / "vosk-x"
    assert (final / "README").read_text() == "hola"
    assert not (tmp_path / "vosk-x.zip.part").exists()


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../fuera.txt", "x")
    with pytest.raises(DownloadError):
        safe_extract(archive, tmp_path / "dest")
    assert not (tmp_path / "fuera.txt").exists()


def test_memory_keeps_last_turns_and_expires() -> None:
    now = [0.0]
    memory = ShortMemory(max_turns=2, expire_s=60, clock=lambda: now[0])
    for i in range(3):
        memory.add(f"p{i}", f"r{i}")
    assert [m.content for m in memory.messages()] == ["p1", "r1", "p2", "r2"]
    now[0] = 61
    assert memory.messages() == []


def test_spanish_datetime() -> None:
    from datetime import datetime

    assert spanish_datetime(datetime(2026, 11, 9, 18, 5)) == "lunes 9 de noviembre de 2026, 18:05"


def test_memory_last_turn_reads_spoken() -> None:
    memory = ShortMemory()
    assert memory.last_turn() is None
    memory.add("¿Qué hora es?", '{"spoken": "Son las siete.", "display": "19:00"}')
    assert memory.last_turn() == ("¿Qué hora es?", "Son las siete.")


def test_download_resumes_after_a_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prueba del 2026-11-18: una conexión cortada a medias ya no tira lo bajado."""
    import hashlib

    import httpx

    import nyx.models as models

    monkeypatch.setattr(models, "_sleep", lambda s: None)
    content = b"0123456789" * 1000
    model = _model(content, name="grande.bin")
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range")
        calls.append(rng)
        if rng is None:
            raise httpx.ReadTimeout("se cortó", request=request)
        start = int(rng.removeprefix("bytes=").rstrip("-"))
        return httpx.Response(206, content=content[start:])

    # La primera vez deja 4.000 bytes en el .part y se corta.
    (tmp_path / "grande.bin.part").write_bytes(content[:4000])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    final = download(model, tmp_path, client=client)
    assert final.read_bytes() == content
    assert calls == ["bytes=4000-"]
    assert hashlib.sha256(final.read_bytes()).hexdigest() == model.sha256


def test_download_retries_and_gives_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    import nyx.models as models

    waits: list[float] = []
    monkeypatch.setattr(models, "_sleep", waits.append)
    model = _model(b"x", name="c.bin")

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    with pytest.raises(DownloadError):
        download(model, tmp_path, client=httpx.Client(transport=httpx.MockTransport(broken)))
    assert len(waits) == models.ATTEMPTS - 1
