"""I/O BLE do iGS10S: device-info SIG + protocolo protobuf proprietário.

Único módulo que fala com o rádio. As funções aceitam um ``BleakClient`` já
conectado — o HA passa o do bleak-retry-connector; a CLI usa ``IGPSClient``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
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

_LOGGER = logging.getLogger(__name__)

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
        self._frames: asyncio.Queue[tuple[p.Header, bytes]] = asyncio.Queue()
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
        payload = b""
        if header.kind == p.FRAME_HEADER:
            payload = bytes(self._buffer)
            self._buffer.clear()
        self._frames.put_nowait((header, payload))

    async def send(
        self,
        service: int,
        op: int,
        payload: bytes,
        sub: int = 0xFF,
        channel: str = p.DATA_RX,
    ) -> None:
        """Escreve payload + header. Descarta frames antigos ainda na fila."""
        while not self._frames.empty():
            self._frames.get_nowait()
        self._buffer.clear()
        # O firmware só lê 20 B por pacote (MTU padrão); o app fatia igual.
        for i in range(0, len(payload), p.PACKET_SIZE):
            chunk = payload[i : i + p.PACKET_SIZE]
            await self._client.write_gatt_char(channel, chunk, response=True)
        await self._client.write_gatt_char(
            p.CONTROL_RX, p.build_header(service, op, payload, sub), True
        )

    async def receive(
        self, service: int, timeout: float = 5.0
    ) -> tuple[p.Header, bytes]:
        """Próximo frame do ``service`` (pushes de outros serviços são ignorados).

        ACK com status != 0 vira ``IGPSCommandError``.
        """
        async with asyncio.timeout(timeout):
            while True:
                header, payload = await self._frames.get()
                if header.service != service:
                    continue
                if header.kind == p.FRAME_ACK and header.status != 0:
                    raise IGPSCommandError(header.status)
                return header, payload

    async def ack(self, service: int, op: int, status: int = 0) -> None:
        await self._client.write_gatt_char(
            p.CONTROL_RX, p.build_ack(service, op, status), True
        )

    async def request(
        self,
        service: int,
        op: int,
        payload: bytes,
        sub: int = 0xFF,
        channel: str = p.DATA_RX,
        timeout: float = 10.0,
    ) -> dict[int, list]:
        """Envia e devolve a resposta decodificada (``{}`` para um ACK de SET)."""
        async with self._lock:
            await self.send(service, op, payload, sub, channel)
            return p.decode((await self.receive(service, timeout))[1])

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
        msg = await s.simple(p.Service.CYCLING_DATA, 1, channel=p.THIRD_RX, timeout=20)
        items = (p.decode(raw) for raw in msg.get(3, []))
        out["activities"] = tuple(
            sorted(
                (
                    Activity(
                        _first(i, 1, 0), fit_time(_first(i, 1, 0)), _first(i, 2, 0)
                    )
                    for i in items
                ),
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


async def download_activity(
    session: IGPSSession,
    activity_id: int,
    size: int | None = None,
    timeout: float = 30.0,
    attempts: int = 3,
) -> bytes:
    """Baixa o ``.fit`` de uma atividade (CYCLING_DATA/FILE_GET no ch3).

    O aparelho manda pedaços de ~4 KB; cada um é confirmado (ACK 0) ou pedido
    de novo (ACK 1) se o CRC/tamanho não bater — igual ao app. Com ``size``
    (da lista de atividades), um arquivo incompleto é baixado de novo.
    """
    for attempt in range(attempts):
        data = await _download_once(session, activity_id, timeout)
        if size is None or len(data) == size:
            return data
        _LOGGER.debug(
            "fit %s incompleto (%d de %d B), tentativa %d",
            activity_id, len(data), size, attempt + 1,
        )  # fmt: skip
    raise IGPSCommandError(1)


async def _download_once(
    session: IGPSSession, activity_id: int, timeout: float
) -> bytes:
    svc, file_get, file_send = p.Service.CYCLING_DATA, 3, 4
    payload, _ = p.request(svc, file_get, [(3, [(1, activity_id)])])
    content = bytearray()
    async with session._lock:
        await session.send(svc, file_get, payload, channel=p.THIRD_RX)
        retries = 0
        while True:
            header, chunk = await session.receive(svc, timeout)
            if header.op != file_send:
                continue
            if len(chunk) != header.length or p.crc8(chunk) != header.payload_crc:
                retries += 1
                _LOGGER.debug(
                    "fit %s: pedaço inválido (%d/%d B), reenvio %d",
                    activity_id, len(chunk), header.length, retries,
                )  # fmt: skip
                if retries > 5:
                    raise IGPSCommandError(1)
                await session.ack(svc, file_send, status=1)
                continue
            retries = 0
            msg = p.decode(chunk)
            if p.decode(_first(msg, 3, b"")).get(1, [activity_id])[0] != activity_id:
                raise IGPSCommandError(1)  # aparelho mandou outra atividade
            content += _first(msg, 4, b"")
            _LOGGER.debug(
                "fit %s: %d B (last=%s)", activity_id, len(content), header.last
            )
            if header.last:
                return bytes(content)
            await session.ack(svc, file_send)


# ------------------------------------------------- atividades / manutenção
#
# Tudo abaixo segue o app (``SyncActivityDelegate``, ``FactorySettingsDelegate``,
# ``PairBindingDelegate``, ``FirmwareUpdateDelegate``). Vários são comandos de
# bancada de fábrica sem tela no app: os nomes vêm dos enums do protobuf.

# Factory.CONTROL_CMD_TYPE (FACTORY/CONTROL_SET).
CONTROL = {
    "enter_check": 1,  # modo de teste de fábrica
    "lock": 2,
    "format": 16,  # formata a memória (apaga atividades)
    "low_level_format": 17,
    "reset_settings": 18,  # PARA_RESET: volta ajustes ao padrão
    "factory_reset": 19,
    "temperature_log": 32,
    "voltage_log": 33,
    "ant_log": 34,
}
# Factory.GPS_CONTROL_CMD_TYPE (FACTORY/GPS_CONTROL_CMD_SET).
GPS_COMMAND = {"power": 1, "cold_start": 2, "power_save": 3, "gnss": 4}
# Factory.GNSS_TYPE — bitmask para FACTORY/GPS_GNSS_SET.
GNSS = {
    "gps": 1, "beidou": 2, "glonass": 4, "qzss": 8,
    "sbas": 16, "galileo": 32, "imes": 64,
}  # fmt: skip
# Factory.GPS_DYNAMIC_TYPE (modelo dinâmico do receptor).
GPS_DYNAMIC = {
    "portable": 1, "stationary": 2, "pedestrian": 3, "automotive": 4, "sea": 5,
    "airborne_1g": 6, "airborne_2g": 7, "airborne_4g": 8, "wrist": 9, "bike": 10,
}  # fmt: skip
# Factory.FILTER_TYPE (FACTORY/FILTER_SET).
FILTERS = {
    "smart_save": 1, "speed": 2, "cadence": 3, "heart_rate": 4,
    "gps_icon": 5, "ant_icon": 6,
}  # fmt: skip
# Comandos que podem reiniciar o aparelho antes de responder.
_REBOOTING = {"format", "low_level_format", "reset_settings", "factory_reset"}


async def command(
    session: IGPSSession,
    service: int,
    op: int,
    fields=(),
    sub: int = 0xFF,
    channel: str = p.DATA_RX,
    timeout: float = 10.0,
) -> dict[int, list]:
    """Comando cru: ``{1: service, 2: op, *fields}`` — para o que não tem helper."""
    return await session.simple(
        service, op, list(fields), sub=sub, channel=channel, timeout=timeout
    )


async def delete_activity(session: IGPSSession, activity_id: int) -> None:
    """Apaga uma atividade (CYCLING_DATA/FILE_DEL no ch3)."""
    await session.simple(
        p.Service.CYCLING_DATA, 5, [(3, [(1, activity_id)])], channel=p.THIRD_RX
    )


async def delete_all_activities(session: IGPSSession) -> None:
    """Apaga todas as atividades (CYCLING_DATA/ALL_DEL no ch3)."""
    await session.simple(p.Service.CYCLING_DATA, 6, channel=p.THIRD_RX)


async def _factory(session: IGPSSession, op: int, field: int, data, **kw) -> None:
    await session.simple(p.Service.FACTORY, op, [(field, data)], **kw)


async def factory_control(session: IGPSSession, cmd: str, status: int = 1) -> None:
    """FACTORY/CONTROL_SET: format, factory_reset, reset_settings, lock, logs…

    Os que reiniciam o aparelho podem não responder: timeout conta como enviado.
    """
    try:
        await _factory(session, 23, 8, [(1, CONTROL[cmd]), (2, status)], timeout=10)
    except TimeoutError:
        if cmd not in _REBOOTING:
            raise


async def gps_control(session: IGPSSession, cmd: str, status: int = 1) -> None:
    """Liga/desliga GPS (``power``), ``cold_start``, ``power_save``, ``gnss``."""
    await _factory(session, 16, 14, [(1, GPS_COMMAND[cmd]), (2, status)])


async def set_gnss(session: IGPSSession, systems) -> None:
    """Constelações ativas, ex. ``{"gps", "glonass", "galileo"}``."""
    mask = 0
    for name in systems:
        mask |= GNSS[name]
    await _factory(session, 18, 15, [(1, mask)])


async def set_gps_dynamic(session: IGPSSession, mode: str) -> None:
    await _factory(session, 20, 16, [(1, GPS_DYNAMIC[mode])])


async def set_gps_position(
    session: IGPSSession, latitude: float, longitude: float
) -> None:
    """Posição de referência (ajuda o primeiro fix)."""
    await _factory(session, 8, 9, [(1, float(latitude)), (2, float(longitude))])


async def set_power_save_time(session: IGPSSession, value: int) -> None:
    """FACTORY/POWER_SAVE_TIME_SET (valor cru do firmware)."""
    await _factory(session, 11, 11, [(1, value)])


async def set_sun_time(session: IGPSSession, sunrise: int, sunset: int) -> None:
    """FACTORY/SUN_TIME_SET (valores crus; usados no backlight automático)."""
    await _factory(session, 9, 10, [(1, sunrise), (2, sunset)])


async def set_filter(session: IGPSSession, name: str, enabled: bool) -> None:
    await _factory(session, 14, 13, [(1, FILTERS[name]), (2, int(enabled))])


async def set_rtc(session: IGPSSession, local: datetime) -> None:
    """FACTORY/RTC_SET. O iGS10S confirma mas o GPS sobrescreve a hora."""
    await _factory(session, 12, 12, [(1, int((local - FIT_EPOCH).total_seconds()))])


async def simulate_activities(session: IGPSSession, count: int, size: int) -> None:
    """FACTORY/SIM_FIT_SET: gera atividades .fit falsas (teste de fábrica)."""
    await _factory(session, 7, 7, [(1, count), (2, size)])


async def set_serial(session: IGPSSession, serial: str) -> None:
    """FACTORY/SN_SET: regrava o número de série."""
    await _factory(session, 3, 3, [(1, serial)])


async def unbond(session: IGPSSession) -> None:
    """BLE/UNBOND: desfaz o vínculo com o app (``sendCancelBonding``)."""
    await session.simple(p.Service.BLE, 4)


async def enter_dfu(session: IGPSSession) -> None:
    """FIRMWARE/BLE_UPDATE: reinicia no bootloader Nordic DFU.

    Lá ele espera um .zip de firmware (ex.: nRF Connect / nrfutil). Costuma
    reiniciar sem responder, então timeout conta como enviado.
    """
    try:
        await session.simple(p.Service.FIRMWARE, 5, timeout=5)
    except TimeoutError:
        pass


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
