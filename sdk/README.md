# nyx-sdk

Kit para hacer extensiones de [Nyx](https://tepnyx.com/nyx), el asistente de voz de Tepnyx.
Licencia MIT: tus extensiones pueden tener la licencia que quieras.

Trae dos cosas:

- **Los tipos de `import nyx`** (`nyx-stubs`), para que el editor y mypy conozcan el módulo
  que Nyx da a tu extensión: `nyx.tool`, `nyx.ask`, `nyx.ask_sync`, `nyx.data_dir`.
- **Un Nyx falso** (`nyx_sdk.testing.FakeNyx`) para probar tus herramientas con pytest sin
  Nyx: apunta lo que pide tu extensión, contesta lo que le digas y, como Nyx, dice que no a
  lo que no esté en los permisos del manifiesto.

```python
from nyx_sdk.testing import FakeNyx


def test_graba() -> None:
    nyx = FakeNyx("mi-extension")
    nyx.answer("ws.open", 1)
    nyx.answer("ws.send", None)
    nyx.answer("ws.recv", lambda p: '{"op": 7, "d": {"requestStatus": {"result": true}}}')
    assert nyx.run("obs_start_recording") == "Grabando."
```

Para crear una extensión, comprobarla, probarla encerrada como en Nyx y empaquetarla está
`nyx-ext` (de momento, `core/scripts/nyx_ext.py` en el repositorio de Nyx). Cómo se hace todo,
paso a paso: `docs/extensiones/README.md`.
