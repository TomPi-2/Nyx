"""7.01: el manifiesto de las extensiones. Lo que no valide no se instala."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nyx.ext.manifest import (
    ManifestError,
    Permission,
    api_compatible,
    load_manifest,
    parse_permission,
)
from nyx.tools.base import GamePolicy, Risk

GOOD: dict[str, Any] = {
    "id": "tepnyx.obs-basico",
    "name": "OBS básico",
    "version": "1.2.0",
    "author": "Tepnyx",
    "nyx_api": ">=1.0 <2.0",
    "kinds": ["tools"],
    "permissions": ["net:localhost:4455", "secrets", "ui:panel"],
    "game_policy": {"obs_scene": "allowed"},
    "groups": [
        {
            "name": "obs",
            "about": "OBS: escenas y directo",
            "keywords": ["obs", "escena", "directo"],
            "tools": ["obs_scene"],
        }
    ],
    "license": {"type": "free", "spdx": "MIT"},
}


def raw(**changes: Any) -> bytes:
    data = {**GOOD, **changes}
    for key, value in list(data.items()):
        if value is None:
            del data[key]
    return json.dumps(data, ensure_ascii=False).encode()


def test_a_good_manifest() -> None:
    m = load_manifest(raw())
    assert m.id == "tepnyx.obs-basico"
    assert m.game_policy == {"obs_scene": GamePolicy.ALLOWED}
    assert m.parsed_permissions[0] == Permission("net", "localhost:4455")
    assert m.version_key() == (1, 2, 0)


def test_no_code_kinds_need_no_permissions() -> None:
    m = load_manifest(
        raw(kinds=["actions", "knowledge"], permissions=None, game_policy=None, groups=None)
    )
    assert m.permissions == ()


@pytest.mark.parametrize(
    ("changes", "why"),
    [
        ({"permissions": ["keyboard:game"]}, "no es un permiso"),  # inventado
        ({"permissions": ["screen"]}, "1.2"),
        ({"permissions": ["ui:widget"]}, "1.1"),
        ({"permissions": ["files:read:C:/Users"]}, "files:read"),  # ruta libre: no
        ({"permissions": ["net:localhost"]}, "net:<servidor>:<puerto>"),
        ({"permissions": ["net:localhost:99999"]}, "net:<servidor>:<puerto>"),
        ({"permissions": ["secrets", "secrets"]}, "repetidos"),
        ({"id": "OBS"}, "id"),
        ({"id": "tepnyx.obs/../../x"}, "id"),
        ({"version": "1.2"}, "version"),
        ({"version": "01.2.3"}, "version"),
        ({"nyx_api": ">=2.0"}, "API"),
        ({"nyx_api": "cualquiera"}, "rango"),
        ({"kinds": []}, "kinds"),
        ({"kinds": ["tools", "tools"]}, "repetidos"),
        ({"kinds": ["widget"]}, "kinds"),
        ({"extra": True}, "extra"),  # campos de más
        ({"kinds": ["actions"]}, "solo las extensiones con herramientas"),
        ({"game_policy": {"obs_scene": "always"}}, "game_policy"),
        ({"license": {"type": "paid"}}, "product"),
        ({"homepage": "http://inseguro.com"}, "homepage"),
        ({"name": ""}, "name"),
        # 7.14: ajustes que pone el usuario
        ({"settings": [{"key": "Clave", "label": "x"}]}, "key"),
        ({"settings": [{"key": "a", "label": "x"}, {"key": "a", "label": "y"}]}, "repetidos"),
        (
            {
                "kinds": ["knowledge"],
                "permissions": [],
                "groups": [],
                "game_policy": {},
                "settings": [{"key": "a", "label": "x"}],
            },
            "settings",
        ),
    ],
)
def test_bad_manifests(changes: dict[str, Any], why: str) -> None:
    with pytest.raises(ManifestError, match=why):
        load_manifest(raw(**changes))


@pytest.mark.parametrize("blob", [b"", b"[]", b"{", b"{}" * 40_000, b"\xff\xfe"])
def test_not_even_json(blob: bytes) -> None:
    with pytest.raises(ManifestError):
        load_manifest(blob)


@pytest.mark.parametrize(
    ("spec", "ok"),
    [
        (">=1.0 <2.0", True),
        ("1.0", True),
        ("==1.0", True),
        (">=1.1", False),
        ("<1.0", False),
        (">0.9 <=1.0", True),
    ],
)
def test_api_ranges(spec: str, ok: bool) -> None:
    assert api_compatible(spec) is ok


def test_permissions_carry_their_minimum_risk() -> None:
    assert parse_permission("messages:discord").min_risk is Risk.RED
    assert parse_permission("files:write:documentos").min_risk is Risk.YELLOW
    assert parse_permission("net:obs.local.example.com:443").target == "obs.local.example.com:443"


def test_an_update_that_asks_for_more() -> None:
    m = load_manifest(raw())
    assert m.new_permissions(["secrets", "ui:panel"]) == ("net:localhost:4455",)
