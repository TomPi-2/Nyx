"""Las extensiones oficiales se prueban con el SDK del repositorio (`sdk/src`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "src"))
