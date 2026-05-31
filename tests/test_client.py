from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from igps_ble.client import IGPSClient
from igps_ble.const import (
    BATTERY_LEVEL_UUID,
    FIRMWARE_REVISION_UUID,
    HARDWARE_REVISION_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
    SOFTWARE_REVISION_UUID,
)


def _fake_bleak_client(reads):
    """BleakClient mock: services presentes p/ os UUIDs em `reads`, reads roteados."""

    async def read_gatt_char(uuid):
        if uuid not in reads:
            raise KeyError(uuid)
        return reads[uuid]

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_gatt_char = AsyncMock(side_effect=read_gatt_char)
    services = MagicMock()
    services.get_characteristic = lambda uuid: object() if uuid in reads else None
    client.services = services
    return client


def _igs10s_reads():
    """O que o iGS10S real expõe (recon 2026-05-31): sem bateria, sem model,
    firmware na Software Revision (0x2A28), hardware na 0x2A27."""
    return {
        MODEL_NUMBER_UUID: b"iGS10S\x00",
        SOFTWARE_REVISION_UUID: b"V1.15",
        HARDWARE_REVISION_UUID: b"V1.00",
        MANUFACTURER_NAME_UUID: b"iGPSPORT",
    }


@pytest.mark.asyncio
async def test_read_state_firmware_from_software_revision():
    fake = _fake_bleak_client(_igs10s_reads())
    with patch("igps_ble.client.BleakClient", return_value=fake):
        client = IGPSClient("AA:BB:CC:DD:EE:FF", name="iGS10S", rssi=-44)
        state = await client.async_read_state()

    assert state.firmware == "V1.15"  # vem do 0x2A28
    assert state.hardware == "V1.00"  # vem do 0x2A27
    assert state.model == "iGS10S"
    assert state.manufacturer == "iGPSPORT"
    assert state.rssi == -44
    assert state.battery_level is None  # iGS10S não tem Battery Service


@pytest.mark.asyncio
async def test_read_state_firmware_falls_back_to_2a26():
    # Aparelho que usa a Firmware Revision (0x2A26) clássica, sem 0x2A28.
    reads = {
        FIRMWARE_REVISION_UUID: b"2.0.1",
        MANUFACTURER_NAME_UUID: b"iGPSPORT",
    }
    fake = _fake_bleak_client(reads)
    with patch("igps_ble.client.BleakClient", return_value=fake):
        client = IGPSClient("AA:BB:CC:DD:EE:FF")
        state = await client.async_read_state()

    assert state.firmware == "2.0.1"


@pytest.mark.asyncio
async def test_read_state_battery_present_is_parsed():
    reads = {**_igs10s_reads(), BATTERY_LEVEL_UUID: bytes([0x57])}
    fake = _fake_bleak_client(reads)
    with patch("igps_ble.client.BleakClient", return_value=fake):
        client = IGPSClient("AA:BB:CC:DD:EE:FF")
        state = await client.async_read_state()

    assert state.battery_level == 87


@pytest.mark.asyncio
async def test_read_state_missing_model_is_none():
    reads = {
        SOFTWARE_REVISION_UUID: b"V1.15",
        MANUFACTURER_NAME_UUID: b"iGPSPORT",
    }
    fake = _fake_bleak_client(reads)
    with patch("igps_ble.client.BleakClient", return_value=fake):
        client = IGPSClient("AA:BB:CC:DD:EE:FF", name="iGS10S")
        state = await client.async_read_state()

    assert state.model is None
    assert state.firmware == "V1.15"
