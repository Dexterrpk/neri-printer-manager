"""Utilitários para impedir que credenciais apareçam em logs e relatórios."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

_URI_USERINFO_RE = re.compile(
    r"(?P<scheme>\b(?:smb|ipp|ipps|http|https)://)(?P<userinfo>[^/@\s]+)@",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)(?P<prefix>\b(?:password|passwd|senha|secret|token|credentials?"
    r"|api[_-]?key|access[_-]?key)\s*[:=]\s*)[^\r\n]*"
)
_AUTH_HEADER_RE = re.compile(
    r"(?im)(?P<prefix>\b(?:authorization|proxy-authorization)\s*:\s*)[^\r\n]*"
)
_UNSAFE_DISPLAY_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SECRET_KEYS = {
    "authorization",
    "credential",
    "credentials",
    "passwd",
    "password",
    "secret",
    "senha",
    "token",
}


def _is_secret_key(value: object) -> bool:
    parts = re.findall(r"[a-z0-9]+", str(value).lower())
    return any(part in _SECRET_KEYS for part in parts)


def redact_text(value: object) -> str:
    """Remove senhas e ``userinfo`` de URIs sem esconder o erro útil."""

    text = str(value or "")
    text = _URI_USERINFO_RE.sub(lambda match: f"{match.group('scheme')}***@", text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group('prefix')}***", text)
    text = _AUTH_HEADER_RE.sub(lambda match: f"{match.group('prefix')}***", text)
    return _UNSAFE_DISPLAY_CONTROL_RE.sub("", text)


def redact_data(value: Any) -> Any:
    """Aplica a remoção de segredos recursivamente a dados serializáveis."""

    if isinstance(value, str):
        raw = value.value if isinstance(value, Enum) else value
        return redact_text(raw)
    if isinstance(value, Mapping):
        return {
            str(key): "***" if _is_secret_key(key) else redact_data(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_data(item) for item in value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_data(item) for item in value]
    return value


def contains_control_characters(value: str) -> bool:
    """Informa se um valor contém caracteres impróprios para credenciais/URIs."""

    return any(ord(character) < 32 or ord(character) == 127 for character in value)
