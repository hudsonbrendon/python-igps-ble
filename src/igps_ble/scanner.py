"""Descoberta BLE do iGS10S (toca o adaptador Bluetooth)."""

from __future__ import annotations

from bleak import BleakScanner

from .const import NAME_PREFIXES
from .models import IGPSDeviceState


def is_igps_device(local_name: str | None) -> bool:
    """True se o nome de advertisement bate com um prefixo conhecido do iGPSPORT."""
    if not local_name:
        return False
    return any(local_name.startswith(prefix) for prefix in NAME_PREFIXES)


async def discover_devices(timeout: float = 10.0) -> list[IGPSDeviceState]:
    """Escaneia e devolve um IGPSDeviceState por aparelho iGPSPORT visto.

    Não conecta — campos de bateria/device-info ficam None aqui.
    """
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    results: list[IGPSDeviceState] = []
    for address, (device, adv) in discovered.items():
        name = adv.local_name or device.name
        if not is_igps_device(name):
            continue
        results.append(
            IGPSDeviceState(address=address, name=name, rssi=adv.rssi)
        )
    return results
