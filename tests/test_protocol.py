"""Frames reais capturados (iPhone ↔ iGS10S e probe ao vivo, 2026-10-25)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from igps_ble import protocol as p
from igps_ble.client import IGPSCommandError, IGPSSession, read_state


def test_header_matches_official_app():
    payload, header = p.request(p.Service.DEV_VER_INFO, 2)
    assert payload.hex() == "08111002"
    assert header.hex() == "0111ffff02ffff0004ad01ffffffffffffffffae"


def test_config_header_uses_sub_service_byte():
    payload = p.encode([(1, 12), (2, 1), (3, 2)])
    assert p.build_header(12, 2, payload, sub=1).hex() == (
        "010c01ff02ffff00063501ffffffffffffffff22"
    )


def test_parse_ack_status():
    ack = p.parse_header(bytes.fromhex("020c01ff02ffff06ffffffffffffffffffffff2a"))
    assert ack.kind == p.FRAME_ACK and ack.status == 6
    assert (
        p.parse_header(bytes.fromhex("020c01ff02ffff06ffffffffffffffffffffff00"))
        is None
    )


def test_negative_varint_roundtrip():
    msg = p.decode(p.encode([(7, -10800)]))
    assert p.int32(msg[7][0]) == -10800


# Respostas reais do iGS10S, por serviço: (notificações de dados, header).
REPLIES = {
    11: {
        6: (["080b1006320508861d1033"], "010bffff06ffff000b3b01ffffffffffffffff7a"),
    },
}


def _fake_device(replies):
    """BleakClient falso: responde ao header com os frames gravados."""
    client = MagicMock()
    callbacks = {}
    written = []

    async def start_notify(char, cb):
        callbacks[char] = cb

    async def write(char, data, response=False):
        written.append((char, bytes(data)))
        if char != p.CONTROL_RX:
            return
        header = p.parse_header(bytes(data))
        reply = replies.get(header.service, {}).get(header.op)
        if reply is None:  # aparelho não suporta: ACK status 6
            ack = bytearray(b"\x02" + bytes([header.service]) + b"\xff" * 18)
            ack[7] = 6
            ack[19] = p.crc8(bytes(ack[:19]))
            asyncio.get_running_loop().call_soon(callbacks[p.CONTROL_TX], None, ack)
            return
        frames, head = reply
        loop = asyncio.get_running_loop()
        for f in frames:
            loop.call_soon(callbacks[p.DATA_TX], None, bytearray.fromhex(f))
        loop.call_soon(callbacks[p.CONTROL_TX], None, bytearray.fromhex(head))

    client.start_notify = start_notify
    client.write_gatt_char = write
    client.read_gatt_char = AsyncMock(return_value=b"V1.15")
    client.services.get_characteristic = lambda uuid: object()
    return client, written


async def test_session_battery_and_chunking():
    client, written = _fake_device(REPLIES)
    session = IGPSSession(client)
    await session.start()
    reply = await session.simple(p.Service.FACTORY, 6)
    battery = p.decode(reply[6][0])
    assert battery == {1: [3718], 2: [51]}

    try:
        await session.simple(p.Service.CONFIG, 2, [(3, b"x" * 30)])
    except IGPSCommandError as err:
        assert err.status == 6
    data_writes = [d for c, d in written if c == p.DATA_RX]
    assert max(len(d) for d in data_writes) <= p.PACKET_SIZE


async def test_read_state_tolerates_unsupported_queries():
    client, _ = _fake_device(REPLIES)
    state = await read_state(client, "AA", "iGS10S")
    assert state.battery_level == 51
    assert state.battery_voltage == 3.718
    assert state.serial is None  # sem resposta gravada => ignorado


def _ack_device():
    """Aparelho falso que responde ACK 0 a tudo e guarda o que foi escrito."""
    client = MagicMock()
    callbacks, written = {}, []

    async def start_notify(char, cb):
        callbacks[char] = cb

    async def write(char, data, response=False):
        written.append((char, bytes(data)))
        if char == p.CONTROL_RX and data[0] == p.FRAME_HEADER:
            ack = p.build_ack(data[1], data[4])
            asyncio.get_running_loop().call_soon(
                callbacks[p.CONTROL_TX], None, bytearray(ack)
            )

    client.start_notify, client.write_gatt_char = start_notify, write
    return client, written


def _payload(written, channel):
    return b"".join(d for c, d in written if c == channel)


async def test_command_payloads_follow_the_app():
    from igps_ble import client as c

    cases = [
        (lambda s: c.delete_activity(s, 1130913501), p.THIRD_RX,
         p.encode([(1, 6), (2, 5), (3, [(1, 1130913501)])])),
        (lambda s: c.delete_all_activities(s), p.THIRD_RX, bytes.fromhex("08061006")),
        (lambda s: c.factory_control(s, "factory_reset"), p.DATA_RX,
         bytes.fromhex("080b1017420408131001")),
        (lambda s: c.set_gnss(s, {"gps", "glonass"}), p.DATA_RX,
         bytes.fromhex("080b10127a020805")),
        (lambda s: c.unbond(s), p.DATA_RX, bytes.fromhex("080a1004")),
        (lambda s: c.enter_dfu(s), p.DATA_RX, bytes.fromhex("08041005")),
    ]  # fmt: skip
    for run, channel, expected in cases:
        client, written = _ack_device()
        session = IGPSSession(client)
        await session.start()
        await run(session)
        assert _payload(written, channel) == expected


def test_double_field():
    raw = p.encode([(1, -5.5)])
    assert raw[0] == 0x09 and len(raw) == 9


async def test_download_retries_truncated_file(monkeypatch):
    from igps_ble import client as c

    replies = iter([b"\x0e" * 6144, b"\x0e" * 22068])
    monkeypatch.setattr(
        c, "_download_once", AsyncMock(side_effect=lambda *a: next(replies))
    )
    data = await c.download_activity(MagicMock(), 1130913501, size=22068)
    assert len(data) == 22068
