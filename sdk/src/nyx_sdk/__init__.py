# SPDX-License-Identifier: MIT
"""Kit para hacer extensiones de Nyx (tarea 7.12).

- `import nyx` dentro de la extensión: lo pone Nyx. Este paquete trae sus tipos (`nyx-stubs`)
  para el editor y mypy.
- `nyx_sdk.testing.FakeNyx`: un Nyx falso para probar las herramientas con pytest.

Crear, comprobar, probar encerrada y empaquetar: `nyx-ext` (docs/extensiones/README.md).
"""

from nyx_sdk.testing import FakeNyx, PermissionDeniedError

__all__ = ["API", "FakeNyx", "PermissionDeniedError"]

#: Versión de la API de extensiones de Nyx que cubre este kit.
API = "1.0"
