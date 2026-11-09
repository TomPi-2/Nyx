"""SafetyGuard, rutas protegidas, deshacer y registro de acciones (SPEC sección 8)."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from nyx.safety.action_log import ActionLog, Decision
from nyx.safety.guard import SafetyGuard, Verdict
from nyx.safety.paths import PathPolicy
from nyx.safety.undo import Undo, UndoStack
from nyx.tools.base import Prepared, Risk
from nyx.wake.vosk_engine import answer


@pytest.fixture
def policy(tmp_path: Path) -> PathPolicy:
    home = tmp_path / "home"
    docs = home / "Documentos"
    docs.mkdir(parents=True)
    return PathPolicy(
        home=home.resolve(),
        protected_trees=[(tmp_path / "Windows").resolve(), (tmp_path / "NyxData").resolve()],
        protected_exact=[home.resolve(), docs.resolve()],
    )


def test_protected_paths(policy: PathPolicy, tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert policy.protected(tmp_path / "Windows" / "System32" / "x.dll")
    assert policy.protected(tmp_path / "NyxData" / "settings.json")
    assert policy.protected(home / "Documentos")  # mover o borrar Documentos entero, no
    assert not policy.protected(home / "Documentos" / "Fondos")  # lo de dentro, sí
    assert policy.protected(Path("C:/"))
    # Escribir dentro de Documentos sí; en una raíz o en el sistema, no.
    assert not policy.protected_target(home / "Documentos" / "Nueva")
    assert policy.protected_target(Path("C:/Nueva"))
    assert policy.protected_target(tmp_path / "Windows" / "Nueva")
    assert policy.inside_user(home / "Documentos" / "a.txt")
    assert not policy.inside_user(tmp_path / "otra")


def test_real_policy_protects_windows() -> None:
    policy = PathPolicy.default([Path.home() / "Documents"])
    assert policy.protected(Path("C:/Windows/System32"))
    assert policy.protected(Path("C:/Program Files/App"))
    assert policy.protected(Path.home() / "Documents")
    assert not policy.protected(Path.home() / "Documents" / "Proyecto")


@pytest.mark.parametrize(
    ("risk", "verdict"),
    [(Risk.GREEN, Verdict.RUN), (Risk.YELLOW, Verdict.RUN_WITH_UNDO), (Risk.RED, Verdict.CONFIRM)],
)
def test_guard_levels(policy: PathPolicy, tmp_path: Path, risk: Risk, verdict: Verdict) -> None:
    file = tmp_path / "home" / "Documentos" / "a.txt"
    decision = SafetyGuard(policy).evaluate(risk, Prepared("x", paths=[file], count=1))
    assert decision.verdict is verdict
    assert not decision.click_only


def test_guard_blocks_protected_even_if_green(policy: PathPolicy, tmp_path: Path) -> None:
    prepared = Prepared("x", targets=[tmp_path / "Windows" / "nueva"])
    assert SafetyGuard(policy).evaluate(Risk.GREEN, prepared).verdict is Verdict.BLOCK
    docs = Prepared("x", paths=[tmp_path / "home" / "Documentos"])
    assert SafetyGuard(policy).evaluate(Risk.RED, docs).verdict is Verdict.BLOCK


def test_guard_click_only(policy: PathPolicy, tmp_path: Path) -> None:
    guard = SafetyGuard(policy)
    many = Prepared("x", paths=[tmp_path / "home" / "Documentos" / "a"], count=51)
    assert guard.evaluate(Risk.RED, many).click_only
    outside = Prepared("x", paths=[tmp_path / "otra" / "a.txt"], count=1)
    assert guard.evaluate(Risk.RED, outside).click_only


def test_prepared_risk_raises_level(policy: PathPolicy) -> None:
    # close_app con cambios sin guardar: de amarilla pasa a roja.
    decision = SafetyGuard(policy).evaluate(Risk.YELLOW, Prepared("x", risk=Risk.RED))
    assert decision.verdict is Verdict.CONFIRM


async def test_undo_stack_expires_and_takes_once() -> None:
    now = [0.0]
    stack = UndoStack(ttl_s=30, clock=lambda: now[0])

    async def action() -> str:
        return "hecho"

    first = stack.push(Undo("a", action))
    second = stack.push(Undo("b", action))
    assert stack.latest() == second
    assert stack.take(first.id) == first
    assert stack.take(first.id) is None  # una sola vez
    now[0] = 31
    assert stack.take() is None  # caducada


def test_action_log_write_read_prune(tmp_path: Path) -> None:
    log = ActionLog(tmp_path)
    log.write(
        tool="move_files", params={"folder": "Descargas"}, decision=Decision.EXECUTED, ok=True
    )
    rows = log.read()
    assert rows[0]["tool"] == "move_files" and rows[0]["decision"] == "executed"
    old = tmp_path / f"{date.today() - timedelta(days=40):%Y-%m-%d}.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    log.prune()
    assert not old.exists() and log.read()


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("si", True),
        ("vale", True),
        ("adelante", True),
        ("no", False),
        ("cancela", False),
        ("si no espera", False),
        ("", None),
        ("[unk]", None),
    ],
)
def test_yes_no_answer(text: str, value: bool | None) -> None:
    assert answer(text) is value
