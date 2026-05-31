"""Parsers puros (sem I/O) para os bytes das characteristics SIG."""

from __future__ import annotations


def parse_battery_level(data: bytes) -> int | None:
    """Battery Level (0x2A19): 1 byte uint8, 0..100. None se ausente/inválido."""
    if not data:
        return None
    value = data[0]
    if value > 100:
        return None
    return value


def decode_device_string(data: bytes) -> str | None:
    """Device Information string UTF-8; remove NUL de padding e espaços."""
    if not data:
        return None
    text = data.decode("utf-8", errors="replace").replace("\x00", "").strip()
    return text or None
