"""Client async que conecta no iGS10S e lê as characteristics em escopo.

Único módulo que abre conexão BLE. Aceita um BleakClient já criado (ou um
BLEDevice) — útil pra reaproveitar a conexão do bleak-retry-connector no HA.
"""

from __future__ import annotations

from bleak import BleakClient

from .const import (
    BATTERY_LEVEL_UUID,
    FIRMWARE_REVISION_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
)
from .models import IGPSDeviceState
from .parser import decode_device_string, parse_battery_level


class IGPSClient:
    """Lê presença/bateria/device-info de um iGS10S via BLE."""

    def __init__(
        self, address: str, name: str = "iGS10S", rssi: int | None = None
    ) -> None:
        self._address = address
        self._name = name
        self._rssi = rssi

    async def async_read_state(self) -> IGPSDeviceState:
        """Conecta, lê o que o aparelho expõe, e devolve o snapshot."""
        async with BleakClient(self._address) as client:
            battery = await self._read(client, BATTERY_LEVEL_UUID)
            model = await self._read(client, MODEL_NUMBER_UUID)
            firmware = await self._read(client, FIRMWARE_REVISION_UUID)
            manufacturer = await self._read(client, MANUFACTURER_NAME_UUID)

        return IGPSDeviceState(
            address=self._address,
            name=self._name,
            rssi=self._rssi,
            battery_level=parse_battery_level(battery) if battery is not None else None,
            model=decode_device_string(model) if model is not None else None,
            firmware=decode_device_string(firmware) if firmware is not None else None,
            manufacturer=(
                decode_device_string(manufacturer)
                if manufacturer is not None
                else None
            ),
        )

    @staticmethod
    async def _read(client: BleakClient, uuid: str) -> bytes | None:
        """Lê a char se ela existir; None se o aparelho não a expõe."""
        if client.services.get_characteristic(uuid) is None:
            return None
        try:
            return await client.read_gatt_char(uuid)
        except Exception:  # noqa: BLE001 - char some/erra => trata como ausente
            return None
