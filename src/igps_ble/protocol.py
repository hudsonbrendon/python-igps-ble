"""iGPSPORT "gen 3" protobuf-over-NUS framing (iGS10S, iGS320, iGS50S, ...).

Reverse engineered from the iGPSPORT Ride Android app (com.qiwu.worldwide.ride
8.06.46, package com.igpsport.blelib) and validated against a real iGS10S.

A request is a protobuf message written to the data channel (NUS #1 RX),
followed by a 20-byte header written to the control channel (NUS #2 RX):

    [0]  0x01 (header)      [1] service        [2] sub-service (0xff = none)
    [3]  0xff               [4] operation      [5] 0xff
    [6]  0xff               [7:9] payload length (big-endian)
    [9]  crc8(payload)      [10] 0x01 (end type = protobuf)
    [11:19] 0xff * 8        [19] crc8(header[0:19])

The device answers the same way (payload notifications first, then the
header on the control channel). A 0x02 frame on the control channel is an
ACK (``ConfirmCommand``): ``02 svc sub ff op ff ff status ...``.

CRC is CRC-8/MAXIM (reflected poly 0x31, init 0).

The protobuf payloads always start with ``1: service`` and ``2: operation``.
Only a tiny wire codec is needed, so we ship one instead of protoc output.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import struct
from typing import Any

# NUS instances. Base 6e40000X-b5a3-f393-e0a9-e50e24dccaYe.
DATA_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
DATA_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CONTROL_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca8e"
CONTROL_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca8e"
THIRD_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca7e"
THIRD_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca7e"
FOURTH_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca6e"
TX_CHARS = (DATA_TX, CONTROL_TX, THIRD_TX, FOURTH_TX)

PACKET_SIZE = 20  # payload chunk per write (firmware ignores the rest)
FRAME_HEADER = 0x01
FRAME_ACK = 0x02


class Service:
    """``Common.service_type_index`` (subset relevant to a bike computer)."""

    FIRMWARE = 4
    CYCLING_DATA = 6
    USER_CONFIG = 9
    BLE = 10
    FACTORY = 11
    CONFIG = 12
    DEV_STATUS = 13
    SENSOR = 14
    DEV_VER_INFO = 17


# --------------------------------------------------------------------- CRC


def crc8(data: bytes) -> int:
    """CRC-8/MAXIM (poly refletido 0x31, init 0)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8C if crc & 1 else crc >> 1
    return crc


def build_header(service: int, op: int, payload: bytes, sub: int = 0xFF) -> bytes:
    """Header de 20 bytes que acompanha ``payload`` no canal de controle."""
    head = (
        bytes([FRAME_HEADER, service, sub, 0xFF, op, 0xFF, 0xFF])
        + len(payload).to_bytes(2, "big")
        + bytes([crc8(payload), 0x01])
        + b"\xff" * 8
    )
    return head + bytes([crc8(head)])


def build_ack(service: int, op: int, status: int = 0, sub: int = 0xFF) -> bytes:
    """``ConfirmCommand``: confirma (0) ou pede reenvio (1) de um pedaço."""
    head = bytes([FRAME_ACK, service, sub, 0xFF, op, 0xFF, 0xFF, status]) + b"\xff" * 11
    return head + bytes([crc8(head)])


@dataclass(frozen=True)
class Header:
    """Header (0x01) ou ACK (0x02) recebido no canal de controle."""

    kind: int
    service: int
    sub: int
    op: int
    length: int
    payload_crc: int
    raw: bytes

    @property
    def last(self) -> bool:
        """Último pedaço de uma transferência de arquivo (end type 3)."""
        return self.raw[10] == 3

    @property
    def status(self) -> int:
        """ACK status byte (``ConfirmCommand.status``)."""
        return self.raw[7]


def parse_header(frame: bytes) -> Header | None:
    """Valida tamanho/CRC e devolve o ``Header``; ``None`` se não for um frame."""
    if len(frame) != 20 or frame[0] not in (FRAME_HEADER, FRAME_ACK):
        return None
    if crc8(frame[:19]) != frame[19]:
        return None
    return Header(
        kind=frame[0],
        service=frame[1],
        sub=frame[2],
        op=frame[4],
        length=int.from_bytes(frame[7:9], "big"),
        payload_crc=frame[9],
        raw=bytes(frame),
    )


# ---------------------------------------------------------------- protobuf


def _varint(value: int) -> bytes:
    value &= (1 << 64) - 1  # negative int32/int64 -> 10-byte two's complement
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def encode(fields: Iterable[tuple[int, Any]]) -> bytes:
    """Encode ``[(field_no, value)]``.

    int -> varint, float -> double, bytes/str -> len-delimited,
    list -> nested message (same shape).
    """
    out = bytearray()
    for number, value in fields:
        if isinstance(value, float):  # double (wire type 1)
            out += _varint(number << 3 | 1) + struct.pack("<d", value)
            continue
        if isinstance(value, bool | int):
            out += _varint(number << 3) + _varint(int(value))
            continue
        if isinstance(value, list):
            raw = encode(value)
        elif isinstance(value, str):
            raw = value.encode()
        else:
            raw = value
        out += _varint(number << 3 | 2) + _varint(len(raw)) + raw
    return bytes(out)


def decode(data: bytes) -> dict[int, list[Any]]:
    """Decode one message level into ``{field_no: [raw values]}``.

    Varints come back as unsigned ints, len-delimited as bytes, fixed as int.
    Callers decide whether bytes are a nested message (``decode`` again).
    """
    out: dict[int, list[Any]] = {}
    i = 0
    value: int | bytes
    while i < len(data):
        key, i = _read_varint(data, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _read_varint(data, i)
        elif wire == 2:
            size, i = _read_varint(data, i)
            value, i = bytes(data[i : i + size]), i + size
        elif wire == 5:
            value, i = int.from_bytes(data[i : i + 4], "little"), i + 4
        elif wire == 1:
            value, i = int.from_bytes(data[i : i + 8], "little"), i + 8
        else:
            raise ValueError(f"unsupported wire type {wire}")
        out.setdefault(number, []).append(value)
    return out


def _read_varint(data: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        if i >= len(data):
            raise ValueError("truncated varint")
        byte = data[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, i
        shift += 7


def int32(value: int) -> int:
    """Reinterpret an unsigned varint as a signed int32/int64."""
    if value >= 1 << 63:
        return value - (1 << 64)
    if value >= 1 << 31 and value < 1 << 32:
        return value - (1 << 32)
    return value


def request(
    service: int, op: int, extra: Iterable[tuple[int, Any]] = (), sub: int = 0xFF
) -> tuple[bytes, bytes]:
    """Return ``(payload, header)`` for a ``{1: service, 2: op, ...}`` request."""
    payload = encode([(1, service), (2, op), *extra])
    return payload, build_header(service, op, payload, sub)
