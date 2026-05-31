from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from igps_ble.client import IGPSClient
from igps_ble.const import (
    BATTERY_LEVEL_UUID,
    FIRMWARE_REVISION_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
)


def _fake_bleak_client():
    """BleakClient mock: services presentes, reads roteados por UUID."""
    reads = {
        BATTERY_LEVEL_UUID: bytes([0x57]),  # 87%
        MODEL_NUMBER_UUID: b"iGS10S\x00",
        FIRMWARE_REVISION_UUID: b"V1.20",
        MANUFACTURER_NAME_UUID: b"iGPSPORT",
    }

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
    # services com os UUIDs disponíveis (para has_char).
    services = MagicMock()
    services.get_characteristic = lambda uuid: object() if uuid in reads else None
    client.services = services
    return client


@pytest.mark.asyncio
async def test_read_state_populates_all_fields():
    fake = _fake_bleak_client()
    with patch("igps_ble.client.BleakClient", return_value=fake):
        client = IGPSClient("AA:BB:CC:DD:EE:FF", name="iGS10S", rssi=-44)
        state = await client.async_read_state()

    assert state.battery_level == 87
    assert state.model == "iGS10S"
    assert state.firmware == "V1.20"
    assert state.manufacturer == "iGPSPORT"
    assert state.rssi == -44


@pytest.mark.asyncio
async def test_read_state_missing_battery_is_none():
    fake = _fake_bleak_client()
    fake.services.get_characteristic = lambda uuid: (
        None if uuid == BATTERY_LEVEL_UUID else object()
    )
    with patch("igps_ble.client.BleakClient", return_value=fake):
        client = IGPSClient("AA:BB:CC:DD:EE:FF", name="iGS10S")
        state = await client.async_read_state()

    assert state.battery_level is None
    assert state.model == "iGS10S"
