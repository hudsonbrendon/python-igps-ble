"""Modelo imutável do estado lido do iGS10S."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UserProfile:
    """``user_config_data_msg`` (serviço USER_CONFIG). Unidades já convertidas."""

    sex: int = 1  # 1 = masculino, 0 = feminino (``isGendar`` no app)
    weight_kg: float = 0.0
    age: int = 0
    height_cm: int = 0
    wheel_mm: int = 0
    bike_weight_kg: float = 0.0
    time_zone_s: int = 0


@dataclass(frozen=True, slots=True)
class Activity:
    """Uma atividade gravada no aparelho (lista do serviço CYCLING_DATA)."""

    id: int  # timestamp FIT cru — identifica a atividade nos comandos
    start: datetime  # horário local do aparelho (naive)
    size: int  # bytes do .fit


@dataclass(frozen=True, slots=True)
class IGPSDeviceState:
    """Snapshot do que a lib conseguiu ler do aparelho.

    Campos opcionais ficam None quando o aparelho não expõe/responde o dado.
    """

    address: str
    name: str
    rssi: int | None = None
    battery_level: int | None = None
    model: str | None = None
    firmware: str | None = None
    hardware: str | None = None
    manufacturer: str | None = None
    # --- protocolo proprietário (protobuf no Nordic UART) ---
    battery_voltage: float | None = None  # V
    serial: str | None = None
    protocol_version: str | None = None
    memory_total: int | None = None  # unidade do aparelho (KB)
    memory_free: int | None = None
    temperature: float | None = None  # °C, sensor interno
    device_time: datetime | None = None  # relógio do aparelho (local, naive)
    cycling_status: str | None = None  # "idle" | "recording" | "paused"
    cycling_start: datetime | None = None
    latitude: float | None = None  # última posição GPS conhecida
    longitude: float | None = None
    ride: dict[str, int] = field(default_factory=dict)  # rt_data_message bruto
    activities: tuple[Activity, ...] | None = None
