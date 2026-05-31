import pytest

from igps_ble.parser import decode_device_string, parse_battery_level


def test_battery_level_reads_single_byte_percent():
    # Padrão SIG 0x2A19: 1 byte uint8 = porcentagem. 0x57 = 87%.
    assert parse_battery_level(bytes([0x57])) == 87


def test_battery_level_zero_and_full():
    assert parse_battery_level(bytes([0x00])) == 0
    assert parse_battery_level(bytes([0x64])) == 100


def test_battery_level_empty_returns_none():
    assert parse_battery_level(b"") is None


def test_battery_level_out_of_range_clamped():
    # Alguns aparelhos devolvem 0xFF ("desconhecido"); tratamos como None.
    assert parse_battery_level(bytes([0xFF])) is None


def test_decode_device_string_strips_nul_and_whitespace():
    # Strings do Device Info vêm UTF-8, às vezes com NUL de padding.
    assert decode_device_string(b"iGS10S\x00") == "iGS10S"
    assert decode_device_string(b"  V1.20 \x00") == "V1.20"


def test_decode_device_string_empty_returns_none():
    assert decode_device_string(b"") is None
    assert decode_device_string(b"\x00\x00") is None
