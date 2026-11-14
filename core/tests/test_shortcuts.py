from pathlib import Path

import pytest

from nyx.brain.base import LLMToolCall
from nyx.brain.router import Route
from nyx.brain.shortcuts import ShortcutStore, learnable, phrase_key
from nyx.events import TextEntered
from nyx.executor import ToolCall
from nyx.tools.base import ToolResult
from nyx.tools.registry import default_registry
from tests.test_pipeline import Harness
from tests.test_pipeline_actions import with_router

RIOT = ToolCall("open_app", {"name": "Cliente de Riot"})


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("Abre Riot Client, por favor.", "abre riot client"),
        ("Oye, pon el aleatorio en Spotify", "pon el aleatorio en spotify"),
        ("Ciérralo", None),  # depende de lo de antes
        ("maximiza esto", None),
        ("abre la anterior", None),
        ("a " * 20, None),  # demasiado larga
    ],
)
def test_phrase_key(text: str, key: str | None) -> None:
    assert phrase_key(text) == key


def test_learnable() -> None:
    assert learnable(RIOT, "green")
    assert not learnable(ToolCall("delete_files", {"folder": "x"}), "red")
    assert not learnable(ToolCall("undo"), "green")
    # Verde solo por «bloquear»: apagar es rojo al prepararlo y aquí no se ve.
    assert not learnable(ToolCall("system_power", {"action": "shutdown"}), "green")
    assert not learnable(ToolCall("app_action", {"action": "close_tab"}), "yellow")  # sin app
    assert learnable(ToolCall("app_action", {"action": "like", "app": "Spotify"}), "yellow")


def test_store_persists_counts_and_forgets(tmp_path: Path) -> None:
    store = ShortcutStore(tmp_path / "s.db")
    assert store.learn("Abre Riot Client.", RIOT, "green") == "abre riot client"
    store.close()
    store = ShortcutStore(tmp_path / "s.db")
    assert store.lookup("abre riot client") == RIOT
    assert store.all()[0].uses == 1
    assert store.forget("abre riot client") and store.lookup("abre riot client") is None
    assert store.learn("bórralo", ToolCall("delete_files", {"folder": "x"}), "red") is None


async def test_llm_action_is_learned_and_then_skips_the_llm(tmp_path: Path) -> None:
    h = Harness()
    executor = with_router(h, None, [ToolResult(ok=True, message="ok")])
    executor.registry = default_registry()  # type: ignore[attr-defined]
    h.p.shortcuts = ShortcutStore(tmp_path / "s.db")
    h.llm.plans = [[LLMToolCall("open_app", {"name": "Cliente de Riot"})]]
    await h.bus.publish(TextEntered("abre riot client"))
    await h.p.wait_idle()
    assert len(h.llm.requests) == 1
    await h.bus.publish(TextEntered("Abre Riot Client."))
    await h.p.wait_idle()
    assert len(h.llm.requests) == 1  # la segunda vez, sin LLM
    assert executor.calls[-1] == RIOT
    await h.p.close()


async def test_undo_right_after_forgets_the_shortcut(tmp_path: Path) -> None:
    h = Harness()
    executor = with_router(h, None, [ToolResult(ok=True, message="ok")])
    executor.registry = default_registry()  # type: ignore[attr-defined]
    store = ShortcutStore(tmp_path / "s.db")
    h.p.shortcuts = store
    h.llm.plans = [[LLMToolCall("open_app", {"name": "Cliente de Riot"})]]
    await h.bus.publish(TextEntered("abre riot client"))
    await h.p.wait_idle()
    assert store.all()
    h.p.router = lambda text: Route([ToolCall("undo")], "undo")
    await h.bus.publish(TextEntered("deshaz"))
    await h.p.wait_idle()
    assert store.all() == []
    await h.p.close()


TWO_STEPS = [LLMToolCall("open_app", {"name": "Spotify"}), LLMToolCall("set_volume", {"level": 20})]


async def test_multi_step_plans_are_learned_as_plans(tmp_path: Path) -> None:
    """7.16: un plan de varios pasos que sale bien se repite sin LLM la próxima vez."""
    h = Harness()
    executor = with_router(h, None, [ToolResult(ok=True, message="ok")] * 2)  # uno por paso
    executor.registry = default_registry()  # type: ignore[attr-defined]
    store = ShortcutStore(tmp_path / "s.db")
    h.p.shortcuts = store
    h.llm.plans = [TWO_STEPS]
    await h.bus.publish(TextEntered("abre spotify y pon el volumen a 20"))
    await h.p.wait_idle()
    assert store.all() == []  # no es un atajo de un paso
    assert len(h.llm.requests) == 1
    executor.calls.clear()
    await h.bus.publish(TextEntered("Abre Spotify y pon el volumen a 20."))
    await h.p.wait_idle()
    assert len(h.llm.requests) == 1  # la segunda vez, sin LLM
    assert [c.name for c in executor.calls] == ["open_app", "set_volume"]
    await h.p.close()


def test_plans_follow_the_shortcut_rules(tmp_path: Path) -> None:
    store = ShortcutStore(tmp_path / "s.db")
    two = [ToolCall("open_app", {"name": "Spotify"}), ToolCall("set_volume", {"level": 20})]
    assert store.learn_plan("abre spotify y sube", two, ["green", "green"]) is not None
    # Un paso rojo, uno que depende del momento o demasiados pasos: no.
    red = [ToolCall("open_app", {"name": "x"}), ToolCall("move_files", {"to": "y"})]
    assert store.learn_plan("abre x y mueve", red, ["green", "red"]) is None
    now = [ToolCall("open_app", {"name": "x"}), ToolCall("close_app", {})]
    assert store.learn_plan("abre x y cierra", now, ["green", "green"]) is None
    many = [ToolCall("set_volume", {"level": i}) for i in range(5)]
    assert store.learn_plan("sube y baja mucho", many, ["green"] * 5) is None
    # Las esperas no se guardan (las vuelve a poner el ejecutor).
    waits = [two[0], ToolCall("wait_for_window", {"name": "Spotify"}), two[1]]
    assert store.learn_plan("abre spotify y baja", waits, ["green", "green", "green"])
    assert [c.name for c in store.lookup_plan("abre spotify y baja") or []] == [
        "open_app",
        "set_volume",
    ]
    # Olvidar también olvida planes.
    assert store.forget("abre spotify y sube") and store.lookup_plan("abre spotify y sube") is None
    assert store.forget_all() == 0 and store.lookup_plan("abre spotify y baja") is None


async def test_an_action_left_for_after_the_game_is_not_learned(tmp_path: Path) -> None:
    """En partida se deja para después: aún no se sabe si funciona (ERRORES.md, 2026-11-14:
    «Põ muusiga» → la web «Spotify», que luego no existía)."""
    h = Harness()
    deferred = ToolResult(ok=True, message="Te lo hago al terminar", data={"deferred": True})
    executor = with_router(h, None, [deferred])
    executor.registry = default_registry()  # type: ignore[attr-defined]
    store = ShortcutStore(tmp_path / "s.db")
    h.p.shortcuts = store
    h.llm.plans = [[LLMToolCall("open_url", {"target": "Spotify"})]]
    await h.bus.publish(TextEntered("pon musica"))
    await h.p.wait_idle()
    assert store.all() == []
    await h.p.close()
