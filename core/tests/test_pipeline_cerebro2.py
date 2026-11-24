"""Pipeline, paso 2 de Cerebro 2: órdenes a medias, ofrecer lo que suena casi igual y la
confianza de Whisper (verificación de «Nyx» y ventana de seguimiento)."""

import asyncio

from nyx.brain.router import Miss, Route
from nyx.events import ActionChosen, TextEntered
from nyx.executor import Executor, ToolCall
from nyx.pipeline import rest_question, unfinished_command
from nyx.stt.base import Transcript, unsure
from nyx.stt.whisper_server import parse_result
from nyx.tools.base import ToolContext
from nyx.tools.registry import ToolRegistry
from tests.test_pipeline import SILENCE, SPEECH, WAKE, FakeSTT, Harness, n
from tests.test_pipeline_safety import Danger, Mover, wait_for_buttons


def test_unfinished_commands() -> None:
    assert unfinished_command("abre la carpeta de")
    assert unfinished_command("Cierra el")
    assert not unfinished_command("abre la carpeta de Descargas")
    assert not unfinished_command("¿qué hora es?")
    assert not unfinished_command("la de")  # no empieza por una orden
    assert rest_question("abre la carpeta de") == "¿Qué carpeta?"
    assert rest_question("abre la") == "¿Qué abro?"
    assert rest_question("cierra el") == "¿Qué cierro?"
    assert rest_question("sube el") == "¿Cuál?"


async def test_unfinished_command_asks_and_joins_the_answer(ctx: ToolContext) -> None:
    h = Harness()
    h.p.executor = Executor(ToolRegistry([Mover()]), ctx)
    heard: list[str] = []

    def router(text: str) -> Route | None:
        heard.append(text)
        return None

    h.p.router = router
    await h.bus.publish(TextEntered("abre la carpeta de"))
    await h.p.wait_idle()
    assert h.bubbles[-1][0] == "¿Qué carpeta?"
    assert heard == []  # no se ha intentado: «No encuentro de.» era el fallo
    await h.bus.publish(TextEntered("Descargas"))
    await h.p.wait_idle()
    assert heard == ["abre la carpeta de Descargas"]
    await h.p.close()


async def test_offer_is_done_with_a_yes(ctx: ToolContext) -> None:
    h = Harness()
    Mover.undone = []
    ex = Executor(ToolRegistry([Danger(), Mover()]), ctx)
    h.p.executor = ex
    ex.confirm = h.p.confirm
    offer = Route([ToolCall("mover")], "open")
    h.p.router = lambda text: Miss("epic gueims", [], offer=offer, offer_name="Epic Games")
    await h.bus.publish(TextEntered("abre epic gueims"))
    yes, _no = await wait_for_buttons(h)
    assert h.bubbles[-1][0] == "¿Querías decir Epic Games?"
    await h.bus.publish(ActionChosen(yes))
    await h.p.wait_idle()
    assert h.bubbles[-1][0] == "Movidos a Documentos"  # se ha hecho
    await h.p.close()


async def test_offer_declined_does_nothing(ctx: ToolContext) -> None:
    h = Harness()
    ex = Executor(ToolRegistry([Mover()]), ctx)
    h.p.executor = ex
    ex.confirm = h.p.confirm
    offer = Route([ToolCall("mover")], "open")
    h.p.router = lambda text: Miss("epic gueims", [], offer=offer, offer_name="Epic Games")
    await h.bus.publish(TextEntered("abre epic gueims"))
    _yes, no = await wait_for_buttons(h)
    await h.bus.publish(ActionChosen(no))
    await h.p.wait_idle()
    assert not h.llm.asked  # ni se ha hecho ni se ha pasado al LLM
    assert "Movidos a Documentos" not in [b[0] for b in h.bubbles]
    await h.p.close()


def test_whisper_confidence_is_read() -> None:
    sure = parse_result(
        {
            "text": " Abre Spotify.",
            "segments": [{"no_speech_prob": 0.01, "avg_logprob": -0.2, "tokens": [1, 2, 3]}],
        }
    )
    assert sure == "Abre Spotify." and not unsure(sure)
    doubt = parse_result(
        {
            "text": "y luego vamos",
            "segments": [
                {"no_speech_prob": 0.05, "avg_logprob": -1.6, "tokens": [1, 2, 3, 4]},
                {"no_speech_prob": 0.7, "avg_logprob": -0.4, "tokens": [5]},
            ],
        }
    )
    assert doubt.no_speech == 0.7 and doubt.unsure
    assert not unsure("texto normal")  # de otro motor: cuenta como seguro
    assert parse_result({"text": "hola"}) == "hola"  # `json` sin trozos


async def test_wake_word_heard_in_noise_is_dropped() -> None:
    stt = FakeSTT(text="Nyx, ¿qué hora es?", clip_text=Transcript("Nyx.", no_speech=0.95))
    h = Harness(stt=stt)
    await h.feed(SILENCE, n(0.5))
    await h.feed(WAKE)
    await h.feed(SPEECH, n(1.0))
    await h.feed(SILENCE, n(1.0))
    await h.p.wait_idle()
    assert h.llm.asked == []  # «Nyx» en ruido: no se atiende
    await h.p.close()


async def test_unsure_followup_is_ignored() -> None:
    h = Harness()
    await h.say()
    await h.p.wait_idle()
    assert len(h.llm.requests) == 1
    # En la ventana de seguimiento, charla de fondo que Whisper no tiene clara.
    h.stt.script = [Transcript("Pon la siguiente.", logprob=-1.8)]
    await h.feed(SILENCE, n(0.3))
    await h.feed(SPEECH, n(0.6))
    await h.feed(SILENCE, n(0.8))
    await h.p.wait_idle()
    await asyncio.sleep(0)
    assert len(h.llm.requests) == 1
    await h.p.close()
