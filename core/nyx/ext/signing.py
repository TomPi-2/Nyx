# SPDX-License-Identifier: GPL-3.0-only OR MIT
# También con licencia MIT (decisión del 2026-11-14), para el kit de extensiones (7.12-7.13).
"""Firma de las extensiones, lista de revocación y modo desarrollador (tarea 7.08).

Decidido por Claude con permiso del usuario (2026-11-14; a confirmar en `docs/REVISAR.md`):

- **Firma Ed25519** (`cryptography`, Apache-2.0/BSD) sobre un resumen del paquete: SHA-256 de
  cada archivo (ruta y contenido), en orden, salvo el propio `signature`. El archivo
  `signature` del `.nyxext` es JSON: `{"key": "<id>", "sig": "<base64>"}`.
- **Las claves públicas de Tepnyx van dentro de Nyx** (`TRUSTED_KEYS`, por id: se pueden
  cambiar sin romper lo firmado antes). La privada nunca está en el repositorio: vive en
  `%APPDATA%\\Tepnyx\\keys\\` del equipo que firma y se usa con `scripts/sign_extension.py`,
  a mano, mientras no haya portal.
- **Sin firma válida**, una extensión solo se instala en modo desarrollador (Ajustes →
  Extensiones), con la etiqueta «sin revisar».
- **Lista de revocación** firmada con las mismas claves (`revoked.json` + `revoked.sig`). Se
  descarga como mucho una vez al día y solo si hay alguna extensión firmada instalada; si una
  está en la lista, se desactiva y se avisa. Si no hay red, vale la última guardada.
"""

from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

SIGNATURE_NAME = "signature"
DIGEST_DOMAIN = b"nyx-extension-v1\n"
REVOCATION_DOMAIN = b"nyx-revocation-v1\n"

#: Claves públicas de Tepnyx (id → clave Ed25519 en base64, 32 bytes), creadas con
#: `scripts/sign_extension.py --nueva-clave`. `tepnyx-1`: la primera, del 2026-11-14.
TRUSTED_KEYS: dict[str, str] = {"tepnyx-1": "9DtxxkwEwK+dVlPIfgo/MZeCs2c/3rBkwSkRmXL3E84="}


class SignatureError(ValueError):
    """La firma no vale. El mensaje es para personas."""


def package_digest(package: Path, members: list[PurePosixPath] | None = None) -> bytes:
    """Resumen del paquete: cada archivo (salvo `signature`) por su ruta, en orden."""
    h = hashlib.sha256(DIGEST_DOMAIN)
    with zipfile.ZipFile(package) as zf:
        names = sorted(
            str(m) for m in (members or [PurePosixPath(i.filename) for i in zf.infolist()])
        )
        for name in names:
            if name == SIGNATURE_NAME or name.endswith("/"):
                continue
            file_hash = hashlib.sha256()
            with zf.open(name) as src:
                while chunk := src.read(1024 * 1024):
                    file_hash.update(chunk)
            h.update(name.encode() + b"\0" + file_hash.digest())
    return h.digest()


def _public_key(key_id: str, trusted: dict[str, str]) -> Ed25519PublicKey:
    raw = trusted.get(key_id)
    if raw is None:
        raise SignatureError("firmada con una clave que no es de Tepnyx")
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw))


def _signed_bytes(digest: bytes, approved: tuple[str, ...]) -> bytes:
    """Lo que se firma: el resumen del paquete y, si los hay, los permisos delicados que Tepnyx
    ha aprobado (2026-11-16). Así nadie puede añadirse uno a una extensión ya firmada."""
    if not approved:
        return digest  # firmas de antes: igual que siempre
    return digest + b"\0approved:" + ",".join(sorted(approved)).encode()


def verify_package(
    package: Path,
    members: list[PurePosixPath] | None = None,
    trusted: dict[str, str] | None = None,
) -> str:
    """Comprueba la firma; devuelve el id de la clave. Lanza `SignatureError` si no vale."""
    return verify_signature(package, members, trusted)[0]


def verify_signature(
    package: Path,
    members: list[PurePosixPath] | None = None,
    trusted: dict[str, str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Comprueba la firma; devuelve (id de la clave, permisos delicados aprobados)."""
    keys = TRUSTED_KEYS if trusted is None else trusted
    try:
        with zipfile.ZipFile(package) as zf:
            raw = zf.read(SIGNATURE_NAME)
    except KeyError as e:
        raise SignatureError("sin firma de Tepnyx") from e
    try:
        data = json.loads(raw)
        key_id, sig = str(data["key"]), base64.b64decode(data["sig"], validate=True)
        approved = tuple(sorted(str(p) for p in data.get("approved", [])))
    except (ValueError, KeyError, TypeError) as e:
        raise SignatureError("la firma está mal formada") from e
    try:
        signed = _signed_bytes(package_digest(package, members), approved)
        _public_key(key_id, keys).verify(sig, signed)
    except InvalidSignature as e:
        raise SignatureError("la firma no coincide: el paquete ha cambiado") from e
    return key_id, approved


def sign_package(
    package: Path, key: Ed25519PrivateKey, key_id: str, approved: tuple[str, ...] = ()
) -> None:
    """Añade (o sustituye) `signature` en el paquete. Solo para `scripts/sign_extension.py`.
    `approved`: los permisos delicados que Tepnyx ha aprobado tras revisar la solicitud."""
    approved = tuple(sorted(set(approved)))
    signed = _signed_bytes(package_digest(package), approved)
    payload: dict[str, object] = {"key": key_id, "sig": base64.b64encode(key.sign(signed)).decode()}
    if approved:
        payload["approved"] = list(approved)
    signature = json.dumps(payload).encode()
    tmp = package.with_suffix(".firmando")
    with zipfile.ZipFile(package) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            if info.filename != SIGNATURE_NAME:
                dst.writestr(info, src.read(info))
        dst.writestr(SIGNATURE_NAME, signature)
    tmp.replace(package)


def public_key_b64(key: Ed25519PrivateKey) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


# --- lista de revocación ---


class Revoked(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    versions: tuple[str, ...] = ("*",)  # «*»: todas
    reason: str = Field(default="", max_length=300)


class RevocationList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    serial: int = Field(ge=0)  # sube con cada lista: nunca se acepta una más vieja
    issued: datetime
    revoked: tuple[Revoked, ...] = ()

    def reason(self, ext_id: str, version: str) -> str | None:
        for item in self.revoked:
            if item.id == ext_id and ("*" in item.versions or version in item.versions):
                return item.reason or "Tepnyx la ha retirado"
        return None


def verify_revocations(
    raw: bytes, signature: bytes, trusted: dict[str, str] | None = None
) -> RevocationList:
    """La lista, si su firma vale (`signature`: JSON como el de los paquetes)."""
    keys = TRUSTED_KEYS if trusted is None else trusted
    try:
        data = json.loads(signature)
        key_id, sig = str(data["key"]), base64.b64decode(data["sig"], validate=True)
        _public_key(key_id, keys).verify(sig, REVOCATION_DOMAIN + hashlib.sha256(raw).digest())
    except (ValueError, KeyError, TypeError, InvalidSignature) as e:
        raise SignatureError("la lista de revocación no está firmada por Tepnyx") from e
    return RevocationList.model_validate_json(raw)


def sign_revocations(raw: bytes, key: Ed25519PrivateKey, key_id: str) -> bytes:
    sig = key.sign(REVOCATION_DOMAIN + hashlib.sha256(raw).digest())
    return json.dumps({"key": key_id, "sig": base64.b64encode(sig).decode()}).encode()
