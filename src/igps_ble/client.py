"""I/O BLE do iGS10S: device-info SIG + protocolo protobuf proprietário.

Único módulo que fala com o rádio. As funções aceitam um ``BleakClient`` já
conectado — o HA passa o do bleak-retry-connector; a CLI usa ``IGPSClient``.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from dataclasses import replace
from datetime import datetime, timedelta

from bleak import BleakClient

from . import protocol as p
from .const import (
    BATTERY_LEVEL_UUID,
    FIRMWARE_REVISION_UUID,
    HARDWARE_REVISION_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
    SOFTWARE_REVISION_UUID,
)
from .models import Activity, IGPSDeviceState, UserProfile
from .parser import decode_device_string, parse_battery_level

# Epoch FIT (1989-12-31 00:00). O aparelho guarda horário *local* nessa base.
FIT_EPOCH = datetime(1989, 12, 31)
CYCLING_STATUS = {0: "idle", 1: "recording", 2: "paused"}
RIDE_FIELDS = {
    1: "speed", 2: "avg_speed", 3: "riding_time", 4: "distance", 5: "cadence",
    6: "heart_rate", 7: "avg_heart_rate", 8: "power", 9: "total_ascent",
    10: "avg_rise", 11: "altitude", 12: "slope", 13: "max_speed",
    14: "max_heart_rate", 15: "avg_cadence", 16: "max_cadence",
    17: "avg_power", 18: "max_power", 19: "course",
}  # fmt: skip


class IGPSCommandError(Exception):
    """O aparelho respondeu com ACK de erro (``DeviceReturnStatus``)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"device returned status {status}")
        self.status = status


def fit_time(seconds: int) -> datetime:
    return FIT_EPOCH + timedelta(seconds=seconds)


def _double(raw: int) -> float:
    return struct.unpack("<d", raw.to_bytes(8, "little"))[0]


def _first(msg: dict, key: int, default=None):
    return msg.get(key, [default])[0]


class IGPSSession:
    """Request/response sobre os canais NUS (um comando por vez)."""

    def __init__(self, client: BleakClient) -> None:
        self._client = client
        self._buffer = bytearray()
        self._waiter: tuple[int, asyncio.Future] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        for char in (p.DATA_TX, p.THIRD_TX):
            await self._client.start_notify(char, self._on_data)
        await self._client.start_notify(p.CONTROL_TX, self._on_control)

    def _on_data(self, _char, data: bytearray) -> None:
        self._buffer += data

    def _on_control(self, _char, data: bytearray) -> None:
        header = p.parse_header(bytes(data))
        if header is None:
            return
        payload = bytes(self._buffer) if header.kind == p.FRAME_HEADER else b""
        if header.kind == p.FRAME_HEADER:
            self._buffer.clear()
        if self._waiter is None or self._waiter[0] != header.service:
            return  # push espontâneo (ex.: bateria) sem comando pendente
        future = self._waiter[1]
        if future.done():
            return
        if header.kind == p.FRAME_ACK and header.status != 0:
            future.set_exception(IGPSCommandError(header.status))
        else:
            future.set_result(payload)

    async def request(
        self,
        service: int,
        op: int,
        payload: bytes,
        sub: int = 0xFF,
        channel: str = p.DATA_RX,
        timeout: float = 5.0,
    ) -> dict[int, list]:
        """Envia e devolve a resposta decodificada (``{}`` para um ACK de SET)."""
        async with self._lock:
            future = asyncio.get_running_loop().create_future()
            self._waiter = (service, future)
            self._buffer.clear()
            try:
                # O firmware só lê 20 B por pacote (MTU padrão); o app fatia igual.
                for i in range(0, len(payload), p.PACKET_SIZE):
                    chunk = payload[i : i + p.PACKET_SIZE]
                    await self._client.write_gatt_char(channel, chunk, response=False)
                await self._client.write_gatt_char(
                    p.CONTROL_RX, p.build_header(service, op, payload, sub), False
                )
                return p.decode(await asyncio.wait_for(future, timeout))
            finally:
                self._waiter = None

    async def simple(self, service: int, op: int, extra=(), **kw) -> dict[int, list]:
        """Mensagem padrão ``{1: service, 2: op, ...}``."""
        payload, _ = p.request(service, op, extra)
        return await self.request(service, op, payload, **kw)


# ------------------------------------------------------------------- reads


async def _sig(client: BleakClient, uuid: str) -> str | None:
    if client.services.get_characteristic(uuid) is None:
        return None
    try:
        return decode_device_string(await client.read_gatt_char(uuid))
    except Exception:  # noqa: BLE001 - char some/erra => ausente
        return None


async def _sig_battery(client: BleakClient) -> int | None:
    if client.services.get_characteristic(BATTERY_LEVEL_UUID) is None:
        return None
    try:
        return parse_battery_level(await client.read_gatt_char(BATTERY_LEVEL_UUID))
    except Exception:  # noqa: BLE001
        return None


async def _read_protocol(s: IGPSSession) -> dict:
    """Cada consulta é independente: falha numa não derruba as outras."""
    out: dict = {}

    async def attempt(fn):
        with contextlib.suppress(IGPSCommandError, TimeoutError, ValueError):
            await fn()

    async def battery():
        msg = p.decode(_first(await s.simple(p.Service.FACTORY, 6), 6, b""))
        out["battery_voltage"] = _first(msg, 1, 0) / 1000 or None
        out["battery_level"] = _first(msg, 2)

    async def serial():
        sn = p.decode(_first(await s.simple(p.Service.FACTORY, 1), 3, b""))
        out["serial"] = _first(sn, 1, b"").decode() or None

    async def version():
        ver = p.decode(_first(await s.simple(p.Service.DEV_VER_INFO, 2), 3, b""))
        if (proto := _first(ver, 6)) is not None:
            out["protocol_version"] = f"{proto // 100}.{proto % 100:02d}"

    async def memory():
        mem = p.decode(_first(await s.simple(p.Service.FACTORY, 5), 5, b""))
        out["memory_total"], out["memory_free"] = _first(mem, 1), _first(mem, 2)

    async def sensors():
        for raw in (await s.simple(p.Service.FACTORY, 4)).get(4, []):
            sensor = p.decode(raw)
            kind, data = _first(sensor, 1), _first(sensor, 2, 0)
            if kind == 2 and data:  # RTC
                out["device_time"] = fit_time(data)
            elif kind == 4:  # TEM, décimos de °C
                out["temperature"] = p.int32(data) / 10

    async def status():
        msg = await s.simple(p.Service.DEV_STATUS, 1)
        cyc = p.decode(_first(msg, 3, b""))
        out["cycling_status"] = CYCLING_STATUS.get(_first(cyc, 1, 0))
        if start := _first(cyc, 2):
            out["cycling_start"] = fit_time(start)
        gps = p.decode(_first(msg, 4, b""))
        if 1 in gps and 2 in gps:
            out["latitude"] = round(_double(gps[1][0]), 6)
            out["longitude"] = round(_double(gps[2][0]), 6)
        rt = p.decode(_first(msg, 5, b""))
        out["ride"] = {
            RIDE_FIELDS[k]: p.int32(v[0]) for k, v in rt.items() if k in RIDE_FIELDS
        }

    async def activities():
        msg = await s.simple(p.Service.CYCLING_DATA, 1, channel=p.THIRD_RX)
        items = (p.decode(raw) for raw in msg.get(3, []))
        out["activities"] = tuple(
            sorted(
                (Activity(fit_time(_first(i, 1, 0)), _first(i, 2, 0)) for i in items),
                key=lambda a: a.start,
                reverse=True,
            )
        )

    for fn in (battery, serial, version, memory, sensors, status, activities):
        await attempt(fn)
    return out


async def read_state(
    client: BleakClient,
    address: str,
    name: str = "iGS10S",
    rssi: int | None = None,
    session: IGPSSession | None = None,
) -> IGPSDeviceState:
    """Lê device-info SIG + tudo que o protocolo proprietário responde.

    Passe ``session`` (já iniciada) para reaproveitar a conexão em comandos.
    """
    firmware = await _sig(client, SOFTWARE_REVISION_UUID) or await _sig(
        client, FIRMWARE_REVISION_UUID
    )
    state = IGPSDeviceState(
        address=address,
        name=name,
        rssi=rssi,
        battery_level=await _sig_battery(client),
        model=await _sig(client, MODEL_NUMBER_UUID),
        firmware=firmware,
        hardware=await _sig(client, HARDWARE_REVISION_UUID),
        manufacturer=await _sig(client, MANUFACTURER_NAME_UUID),
    )
    if session is None:
        session = IGPSSession(client)
        try:
            await session.start()
        except Exception:  # noqa: BLE001 - aparelho sem NUS => só SIG
            return state
    return replace(state, **await _read_protocol(session))


# ---------------------------------------------------------------- commands


async def set_profile(session: IGPSSession, profile: UserProfile) -> None:
    """Grava o perfil inteiro (USER_CONFIG/SET).

    O iGS10S aceita o SET mas o GET devolve sempre zeros, então não dá pra
    fazer read-modify-write: quem chama guarda o perfil. Campo ausente = 0.
    ``time_zone_s`` define o fuso do relógio (que vem do GPS).
    """
    data = [
        (1, profile.sex),
        (2, round(profile.weight_kg * 10)),
        (3, profile.age),
        (4, profile.height_cm),
        (5, profile.wheel_mm),
        (6, round(profile.bike_weight_kg * 10)),
        (7, profile.time_zone_s),
    ]
    await session.simple(p.Service.USER_CONFIG, 1, [(3, data)])


class IGPSClient:
    """Conveniência p/ CLI: abre a conexão, lê tudo e desconecta."""

    def __init__(
        self, address: str, name: str = "iGS10S", rssi: int | None = None
    ) -> None:
        self._address = address
        self._name = name
        self._rssi = rssi

    async def async_read_state(self) -> IGPSDeviceState:
        async with BleakClient(self._address) as client:
            return await read_state(client, self._address, self._name, self._rssi)
