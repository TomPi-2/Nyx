"""Aviso de arranque cuando falta algo (services.startup_notice)."""

from nyx.services import startup_notice


def test_sin_problemas_no_hay_aviso() -> None:
    assert startup_notice([]) is None


def test_un_problema_titulo_y_que_hacer() -> None:
    assert startup_notice(["mic"]) == (
        "No puedo oírte",
        "No encuentro el micrófono. Mientras, escríbeme con Win + Alt + N.",
    )
    title, detail = startup_notice(["tts"]) or ("", "")
    assert title == "No puedo hablar" and "por escrito" in detail


def test_sin_oido_no_se_repite_la_activacion() -> None:
    # Sin transcripción ni detección de voz es un único «no puedo oírte».
    title, _ = startup_notice(["hear", "hear", "wake", "wake_word:zorblax"]) or ("", "")
    assert title == "No puedo oírte"


def test_varios_problemas_una_linea_por_cada_uno() -> None:
    title, detail = startup_notice(["llm", "tts", "mic"]) or ("", "")
    assert title == "Funciono a medias"
    lines = detail.split("\n")
    assert lines[0].startswith("No puedo oírte.")
    assert any(line.startswith("No puedo hablar.") for line in lines)
    assert any("Ollama" in line for line in lines)


def test_palabra_no_valida() -> None:
    title, detail = startup_notice(["wake_word:zorblax"]) or ("", "")
    assert title == "No respondo a «zorblax»" and "«Nyx»" in detail


def test_sin_nombres_tecnicos() -> None:
    _, detail = startup_notice(["hear", "wake", "tts"]) or ("", "")
    for word in ("whisper", "Silero", "Vosk", "Piper"):
        assert word not in detail


def test_cerebro_sin_ollama_con_su_codigo() -> None:
    # Con llama-server (C5.1) no se habla de Ollama: falta el cerebro o no arranca (N-410), o
    # va con el procesador (N-411).
    title, detail = startup_notice(["llm_local"]) or ("", "")
    assert title == "Aún no puedo pensar" and detail.startswith("N-410")
    assert "Ollama" not in detail
    title, detail = startup_notice(["llm_cpu"]) or ("", "")
    assert title == "Pienso despacio" and detail.startswith("N-411")


def test_el_motor_sale_de_los_ajustes() -> None:
    from nyx.brain.llamacpp import LlamaCppEngine
    from nyx.brain.ollama import OllamaEngine
    from nyx.services import make_llm
    from nyx.settings.model import Settings

    settings = Settings()
    assert isinstance(make_llm(settings), OllamaEngine)  # por defecto, hasta medirlo
    settings.llm.engine = "llamacpp"
    assert isinstance(make_llm(settings), LlamaCppEngine)
