from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from igps_ble.scanner import discover_devices, is_igps_device


def _adv(local_name, rssi=-50, service_uuids=None):
    return SimpleNamespace(
        local_name=local_name, rssi=rssi, service_uuids=service_uuids or []
    )


def test_is_igps_device_matches_known_prefixes():
    assert is_igps_device("iGS10S") is True
    assert is_igps_device("iGPSPORT iGS10S") is True
    assert is_igps_device("iGS520") is True


def test_is_igps_device_rejects_others():
    assert is_igps_device("JBL Charge 5") is False
    assert is_igps_device("") is False
    assert is_igps_device(None) is False


@pytest.mark.asyncio
async def test_discover_devices_filters_and_maps():
    bledev = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="iGS10S")
    other = SimpleNamespace(address="11:22:33:44:55:66", name="TV")
    discovered = {
        "AA:BB:CC:DD:EE:FF": (bledev, _adv("iGS10S", rssi=-44)),
        "11:22:33:44:55:66": (other, _adv("TV", rssi=-70)),
    }
    with patch(
        "igps_ble.scanner.BleakScanner.discover",
        new=AsyncMock(return_value=discovered),
    ):
        results = await discover_devices(timeout=1.0)

    assert len(results) == 1
    state = results[0]
    assert state.address == "AA:BB:CC:DD:EE:FF"
    assert state.name == "iGS10S"
    assert state.rssi == -44
    assert state.battery_level is None  # scan não conecta
