"""Cuándo deja Nyx de escuchar: petición completa tras una pausa y ventana de seguimiento."""

from nyx.events import NyxState
from nyx.pipeline import is_filler
from tests.test_pipeline import SILENCE, SPEECH, WAKE, Harness, n


async def test_keeps_talking_after_complete_question_is_ignored() -> None:
    # «Nix, ¿qué hora es?» … y sigue hablando con otra persona sin pausa larga.
    h = Harness()
    h.stt.script = ["Nix, ¿qué hora es?", "Nix, ¿qué hora es? Oye, y luego vamos al cine."]
    await h.feed(SILENCE, n(0.5))
    await h.feed(WAKE)
    await h.feed(SPEECH, n(1.0))
    await h.feed(SILENCE, n(0.45))  # pausa corta: la pregunta ya está completa
    await h.feed(SPEECH, n(3.0))  # sigue hablando, pero ya no a Nyx
    await h.p.wait_idle()
    assert [r[-1].content for r in h.llm.requests] == ["¿Qué hora es?"]
    # Seguía hablando cuando se abrió la ventana de seguimiento: no cuenta.
    await h.feed(SPEECH, n(1.5))
    assert len(h.llm.requests) == 1
    await h.p.close()


async def test_incomplete_phrase_keeps_listening() -> None:
    h = Harness()
    h.stt.script = ["Nix, pon", "Nix, ¿cómo se dice hola en alemán?"]
    await h.feed(SILENCE, n(0.5))
    await h.feed(WAKE)
    await h.feed(SPEECH, n(0.5))
    await h.feed(SILENCE, n(0.45))  # duda a mitad de frase
    await h.feed(SPEECH, n(1.0))
    await h.feed(SILENCE, n(0.7))
    await h.p.wait_idle()
    assert [r[-1].content for r in h.llm.requests] == ["¿Cómo se dice hola en alemán?"]
    await h.p.close()


async def test_pause_transcription_is_reused_when_user_stops() -> None:
    h = Harness()
    await h.say()  # 1 s de voz + 0,7 s de silencio: hay transcripción en la pausa
    await h.p.wait_idle()
    assert len(h.stt.full_calls) == 1  # no se transcribe dos veces
    await h.p.close()


async def test_followup_filler_is_ignored() -> None:
    h = Harness()
    await h.say()
    await h.p.wait_idle()
    h.stt.script = ["Vale."]
    await h.feed(SILENCE, n(0.3))
    await h.feed(SPEECH, n(0.5))
    await h.feed(SILENCE, n(0.8))
    await h.p.wait_idle()
    assert len(h.llm.requests) == 1  # «vale» no llega al LLM
    assert h.p.state is NyxState.IDLE
    await h.p.close()


async def test_followup_not_addressed_to_nyx_is_ignored() -> None:
    h = Harness()
    await h.say()
    await h.p.wait_idle()
    said = list(h.tts.said)
    h.stt.script = ["Mañana quedamos a las cinco con Pablo."]
    h.llm.addressed = False
    await h.feed(SILENCE, n(0.3))
    await h.feed(SPEECH, n(1.0))
    await h.feed(SILENCE, n(0.8))
    await h.p.wait_idle()
    assert len(h.llm.classified) == 1
    assert "Mañana quedamos" in h.llm.classified[0]
    assert "En alemán se dice Hallo." in h.llm.classified[0]  # con el contexto del turno
    assert len(h.llm.requests) == 1  # no se le responde
    assert h.tts.said == said
    assert h.p.state is NyxState.IDLE
    await h.p.close()


async def test_wake_word_requests_are_not_classified() -> None:
    h = Harness()
    await h.say()
    await h.p.wait_idle()
    assert h.llm.classified == []  # con «Nyx» delante, siempre va dirigida a Nyx
    await h.p.close()


async def test_followup_addressed_to_nyx_is_answered() -> None:
    h = Harness()
    await h.say()
    await h.p.wait_idle()
    h.stt.script = ["¿Y en francés?"]
    await h.feed(SILENCE, n(0.3))
    await h.feed(SPEECH, n(1.0))
    await h.feed(SILENCE, n(0.8))
    await h.p.wait_idle()
    assert len(h.llm.requests) == 2
    assert len(h.tts.said) == 2
    await h.p.close()


def test_fillers() -> None:
    assert is_filler("Vale.") and is_filler("Sí, claro") and not is_filler("¿Y en francés?")
