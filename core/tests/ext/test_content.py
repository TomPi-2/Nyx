"""7.03: tipos sin código. Lo que no valida no se carga; un archivo malo no tumba el resto."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nyx.ext.content import builtin_dir, load_content
from nyx.ext.manifest import load_manifest
from nyx.tools import app_catalog


def ext(tmp: Path, kinds: list[str], files: dict[str, Any]) -> tuple[Any, Path]:
    manifest = {
        "id": "alguien.prueba",
        "name": "Prueba",
        "version": "1.0.0",
        "author": "Alguien",
        "nyx_api": "1.0",
        "kinds": kinds,
    }
    for rel, content in files.items():
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return load_manifest(json.dumps(manifest).encode()), tmp


FIGMA = {
    "apps": [
        {
            "name": "Figma",
            "processes": ["Figma.exe"],
            "names": ["figma"],
            "actions": {
                "zoom_in": {"label": "Ampliar", "keys": "ctrl+plus"},
                "search": {"label": "Buscar", "keys": {"es": "ctrl+b", "en": "ctrl+f"}},
            },
        }
    ]
}


def test_the_builtin_catalog_is_an_extension() -> None:
    folder = builtin_dir() / "tepnyx.apps"
    manifest = load_manifest((folder / "manifest.json").read_bytes())
    content = load_content(manifest, folder)
    assert content.problems == []
    assert [p.name for p in content.profiles] == [p.name for p in app_catalog.PROFILES]
    notepad = app_catalog.profile_for("notepad.exe")
    assert notepad is not None and notepad.actions["save"].keys_for("es") == "ctrl+g"


def test_actions_from_an_extension(tmp_path: Path) -> None:
    content = load_content(*ext(tmp_path, ["actions"], {"actions.json": FIGMA}))
    assert content.problems == []
    (figma,) = content.profiles
    assert figma.processes == frozenset({"figma.exe"})
    assert figma.actions["search"].keys_for("es") == "ctrl+b"
    app_catalog.set_extension_profiles(content.profiles)
    try:
        assert app_catalog.profile_for("figma.exe") is figma
        assert "zoom_in" in app_catalog.all_actions()
    finally:
        app_catalog.set_extension_profiles([])
    assert app_catalog.profile_for("figma.exe") is None


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"keys": "ctrl+teclarara"}, "desconocida"),
        ({"keys": "alt+f4"}, "close_app"),
        ({"keys": "win+l"}, "bloquea"),
        ({"keys": "shift+delete"}, "papelera"),
        ({"keys": {"es": "ctrl+b"}}, "«\\*» o «en»"),
        ({"label": ""}, "label"),
        ({"run": "calc.exe"}, "run"),  # campos de más
    ],
)
def test_bad_actions(tmp_path: Path, change: dict[str, Any], why: str) -> None:
    bad = json.loads(json.dumps(FIGMA))
    bad["apps"][0]["actions"]["zoom_in"] = {**bad["apps"][0]["actions"]["zoom_in"], **change}
    content = load_content(*ext(tmp_path, ["actions"], {"actions.json": bad}))
    assert content.profiles == []
    assert len(content.problems) == 1 and why.replace("\\", "") in content.problems[0]


@pytest.mark.parametrize("process", ["nyx.exe", "Nyx-UI.exe", "cmd", "../x.exe"])
def test_no_actions_on_nyx_or_odd_processes(tmp_path: Path, process: str) -> None:
    bad = json.loads(json.dumps(FIGMA))
    bad["apps"][0]["processes"] = [process]
    content = load_content(*ext(tmp_path, ["actions"], {"actions.json": bad}))
    assert content.profiles == [] and content.problems


def test_presets_only_touch_editable_settings(tmp_path: Path) -> None:
    good = {
        "name": "Silenciosa",
        "settings": {"tts": {"enabled": False}, "responses": {"tone": "neutro"}},
    }
    content = load_content(*ext(tmp_path, ["preset"], {"presets/silenciosa.json": good}))
    assert content.problems == []
    assert content.presets["silenciosa"].settings == good["settings"]


@pytest.mark.parametrize(
    "settings",
    [
        {"game": {"policies": {"delete_files": "allowed"}}},  # seguridad del modo partida
        {"privacy": {"usage_data": True}},
        {"llm": {"model": "otro"}},
        {"web": {"search_url": "https://malo.example/?q={q}"}},
        {"wake": {"custom_word": "hola"}},
        {"appearance": {"glass": {"show_in_captures": True}}},
        {"tts": {"speed": 9}},  # fuera de rango
        {"appearance": {"nyx_color": "fucsia-inventado"}},
    ],
)
def test_bad_presets(tmp_path: Path, settings: dict[str, Any]) -> None:
    preset = {"name": "Mala", "settings": settings}
    content = load_content(*ext(tmp_path, ["preset"], {"presets/mala.json": preset}))
    assert content.presets == {} and content.problems


def test_knowledge(tmp_path: Path) -> None:
    text = "# Guía\n\n## Controles\n\nSalta con espacio.\n\n## Vacío\n\n"
    content = load_content(*ext(tmp_path, ["knowledge"], {"knowledge/guia.md": text}))
    assert content.knowledge == {"prueba controles": "Salta con espacio."}


def test_knowledge_too_big(tmp_path: Path) -> None:
    text = "## A\n\n" + "x" * 70_000
    content = load_content(*ext(tmp_path, ["knowledge"], {"knowledge/guia.md": text}))
    assert content.knowledge == {} and "demasiado grande" in content.problems[0]


def test_personality(tmp_path: Path) -> None:
    good = {
        "name": "Pirata",
        "tone": "divertido",
        "phrases": {"thanks": ["¡A tus órdenes, grumete!"]},
    }
    content = load_content(*ext(tmp_path, ["personality"], {"personality.json": good}))
    assert content.personality is not None and content.personality.tone == "divertido"


@pytest.mark.parametrize(
    "text", ["<script>alert(1)</script>", "Visita https://malo.example", "{{system}}", "`rm`"]
)
def test_personality_is_plain_text(tmp_path: Path, text: str) -> None:
    bad = {"name": "Mala", "phrases": {"thanks": [text]}}
    content = load_content(*ext(tmp_path, ["personality"], {"personality.json": bad}))
    assert content.personality is None and content.problems


def test_one_bad_file_does_not_sink_the_rest(tmp_path: Path) -> None:
    files = {"actions.json": "{roto", "knowledge/a.md": "## Uno\n\nTexto."}
    content = load_content(*ext(tmp_path, ["actions", "knowledge"], files))
    assert content.profiles == [] and content.knowledge == {"prueba uno": "Texto."}
    assert len(content.problems) == 1 and "JSON" in content.problems[0]
