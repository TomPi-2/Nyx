r"""Catálogo de datos para entrenar «Nyx» (fase 4b). Solo licencias libres (decidido el
2026-11-10): nada de los modelos ni de los datos de openWakeWord (CC BY-NC-SA).

Todo va a %LOCALAPPDATA%\Nyx\training\datos\. La huella SHA-256 se fija tras la primera
descarga (`sha256` vacío = aún sin fijar: download.py la imprime para copiarla aquí).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nyx.paths import local_dir

PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
SLR = "https://openslr.trmal.net/resources"
OWW = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"


@dataclass(frozen=True, slots=True)
class Source:
    key: str
    url: str
    license: str
    use: str  # positivos | negativos | ruido | rasgos
    sha256: str = ""
    extract: bool = False

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[1]

    def path(self, root: Path | None = None) -> Path:
        root = root or data_dir()
        # Los .zip se descomprimen en la carpeta de la fuente; el marcador dice que terminó.
        name = self.filename + ".ok" if self.extract else self.filename
        return root / self.key / name


def data_dir() -> Path:
    return local_dir() / "training" / "datos"


def _voice(key: str, path: str, license: str, onnx: str, config: str) -> tuple[Source, Source]:
    return (
        Source(key, f"{PIPER}/{path}.onnx", license, "positivos", onnx),
        Source(key, f"{PIPER}/{path}.onnx.json", license, "positivos", config),
    )


SOURCES: tuple[Source, ...] = (
    # Rasgos de audio de openWakeWord: código Apache-2.0 y modelo base de Google Apache-2.0.
    # (Los modelos de palabras y los negativos precalculados de openWakeWord NO se usan.)
    Source(
        "oww",
        f"{OWW}/melspectrogram.onnx",
        "Apache-2.0 (repositorio openWakeWord)",
        "rasgos",
        "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    ),
    Source(
        "oww",
        f"{OWW}/embedding_model.onnx",
        "Apache-2.0 (Google speech_embedding)",
        "rasgos",
        "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
    ),
    # Voces de Piper para los «Nyx» sintéticos (licencia del conjunto de datos de cada voz).
    *_voice(
        "piper-davefx",
        "es/es_ES/davefx/medium/es_ES-davefx-medium",
        "CC0",
        "d2c9224e122321aac3c33343957fff4d0f465226cb74c66b0f520ca3f8c0dd07",
        "531c4051502e1acbc10b42437f11679bfce9e3919e1796e51fabd73e01e7fd2e",
    ),
    *_voice(
        "piper-carlfm",
        "es/es_ES/carlfm/x_low/es_ES-carlfm-x_low",
        "dominio público",
        "d69677323a907cd4963f42b29c20a98b5d6bfa7f3e64df339915e4650c00d125",
        "d9bdfa9ff01eb2bc9e62e7d2593939d1e4c4d8eb7cf75f972731539d12399966",
    ),
    *_voice(
        "piper-ald",
        "es/es_MX/ald/medium/es_MX-ald-medium",
        "Unlicense",
        "019b3803293c93e34a206dd2e53a3889209a514e786fd7144f7b70196c579b63",
        "5a71498158e04afc8099bfd019c7e87c68eb9d042505a2b1a87e5c1ac2b1a61d",
    ),
    *_voice(
        "piper-sharvard",
        "es/es_ES/sharvard/medium/es_ES-sharvard-medium",
        "CC BY 3.0",
        "234dc4cf0fdb53ccb76b9b2c4d7ef1330364762674c1b78c1b62d8608c528a54",
        "1910940c6b480e0f7cbce5e0da45c8cbe2557ccbfd86a5d22cda141a3b65f521",
    ),
    *_voice(
        "piper-libritts",
        "en/en_US/libritts/high/en_US-libritts-high",
        "CC BY 4.0",
        "9127a559e11603f10b366d1a20ac7426826081dbc521de4c2420c57728d73f0f",
        "2efdc6d7f954588b8180132cbd9b8001933fdd00932c92bc92fd0d2028a9eb3d",
    ),
    # Reverberación y ruidos (OpenSLR 28).
    Source(
        "rirs",
        f"{SLR}/28/rirs_noises.zip",
        "Apache-2.0",
        "ruido",
        "3b50cfde915b3984738169b4beb341e9f6b8062ae4c2076146c5db71c2c05dc7",
        extract=True,
    ),
    # Habla en español para los negativos (OpenSLR 61, 71, 72; Google, CC BY-SA 4.0).
    Source(
        "slr61",
        f"{SLR}/61/es_ar_female.zip",
        "CC BY-SA 4.0",
        "negativos",
        "9cc0f2895d6466c478af9a393def99a9ff4688f26593bbfbb5468eb21627bf08",
        extract=True,
    ),
    Source(
        "slr61",
        f"{SLR}/61/es_ar_male.zip",
        "CC BY-SA 4.0",
        "negativos",
        "9f0cd8441370ce6a7fe2693c306a83d699d7d05608170f8a1d42b0556bf3d9bc",
        extract=True,
    ),
    Source(
        "slr71",
        f"{SLR}/71/es_cl_female.zip",
        "CC BY-SA 4.0",
        "negativos",
        "23593f3dac085d26f99df38159c1ab0ae2c23f5c97ad869292496abc6e171bc6",
        extract=True,
    ),
    Source(
        "slr71",
        f"{SLR}/71/es_cl_male.zip",
        "CC BY-SA 4.0",
        "negativos",
        "ace2cbd6df28e94fdd636ba1263b72b557722b0d2abcf4c6e072011ac870cbee",
        extract=True,
    ),
    Source(
        "slr72",
        f"{SLR}/72/es_co_female.zip",
        "CC BY-SA 4.0",
        "negativos",
        "03721aa7b6b7fe1dd309a0c545cbef4898fac99ed811f4e1769b2fc16bb7eb70",
        extract=True,
    ),
    Source(
        "slr72",
        f"{SLR}/72/es_co_male.zip",
        "CC BY-SA 4.0",
        "negativos",
        "2e72abf283adf3f52c28d9f4d59709d4a24fa57243dc696a99dfbc1b8e534c9a",
        extract=True,
    ),
)
