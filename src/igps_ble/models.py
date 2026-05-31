"""Modelo imutável do estado lido do iGS10S."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IGPSDeviceState:
    """Snapshot do que a lib conseguiu ler do aparelho.

    Campos opcionais ficam None quando o aparelho não expõe a characteristic
    correspondente (ex.: sem Battery Service => battery_level None).
    """

    address: str
    name: str
    rssi: int | None = None
    battery_level: int | None = None
    model: str | None = None
    firmware: str | None = None
    manufacturer: str | None = None
