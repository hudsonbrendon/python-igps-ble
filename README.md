<p align="center">
  <img src="assets/igpsport-logo.png" alt="iGPSPORT" width="420">
</p>

# python-igps-ble

[![CI](https://github.com/hudsonbrendon/python-igps-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/hudsonbrendon/python-igps-ble/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/python-igps-ble)](https://pypi.org/project/python-igps-ble/)
[![Python](https://img.shields.io/pypi/pyversions/python-igps-ble)](https://pypi.org/project/python-igps-ble/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Read what an **iGPSPORT iGS10S** cycling computer exposes over Bluetooth LE from
Python — presence, device info (manufacturer, hardware revision, firmware), and
battery level when the device advertises a Battery Service.

This library powers the
[**iGPSPORT iGS10S Home Assistant integration**](https://github.com/hudsonbrendon/ha-igps-ble),
but works standalone in any async Python project (or straight from the command line).

> The iGS10S keeps its ride data (speed, distance, battery) behind an
> authenticated, proprietary Nordic UART sync used by the official iGPSPORT app —
> that is **out of scope**. See
> [`ha-igps-ble/docs/PROTOCOL.md`](https://github.com/hudsonbrendon/ha-igps-ble/blob/main/docs/PROTOCOL.md)
> for the reverse-engineering notes.

## Features

- 🔌 **Async BLE control** built on [`bleak`](https://github.com/hbldh/bleak) —
  works on Linux, macOS, and Windows.
- 🔍 **Discovery helper** — `discover_devices()` finds nearby iGPSPORT devices
  (presence + RSSI).
- 🏷️ **Device info** — manufacturer, hardware revision, and firmware (read from
  the standard Device Information Service).
- 🔋 **Battery** — battery level when the device exposes the standard Battery
  Service (the iGS10S does not — see below).
- 🖥️ **CLI** — `igps-ble scan / info` for quick testing.

## Requirements

- Python **3.11** or newer.
- A Bluetooth LE adapter (built-in or USB).
- An iGPSPORT iGS10S (other iGPSPORT models exposing the same standard services
  may also work).

## Installation

```bash
pip install python-igps-ble
```

## CLI usage

```bash
igps-ble scan                      # find nearby iGPSPORT devices
igps-ble info AA:BB:CC:DD:EE:FF     # connect and read battery + device info
```

## Library usage

```python
import asyncio
from igps_ble import IGPSDeviceState
from igps_ble.scanner import discover_devices
from igps_ble.client import IGPSClient


async def main():
    for dev in await discover_devices(timeout=10):
        state: IGPSDeviceState = await IGPSClient(
            dev.address, dev.name
        ).async_read_state()
        print(state.manufacturer, state.model, state.firmware, state.battery_level)


asyncio.run(main())
```

`IGPSClient` accepts a `bleak` `BLEDevice` (preferred — e.g. from Home Assistant's
shared scanner or a Bluetooth proxy) or a string MAC/UUID address.

### API

| Symbol | Description |
|---|---|
| `discover_devices(timeout=10.0)` | List nearby iGPSPORT devices as `IGPSDeviceState` (presence + RSSI; does not connect). |
| `is_igps_device(local_name)` | `True` if an advertisement name matches a known iGPSPORT prefix. |
| `IGPSClient(address, name="iGS10S", rssi=None)` | Async client; `await client.async_read_state()` connects and returns an `IGPSDeviceState`. |
| `IGPSDeviceState` | Frozen dataclass: `address`, `name`, `rssi`, `battery_level`, `model`, `firmware`, `hardware`, `manufacturer`. |
| `parse_battery_level(data)` / `decode_device_string(data)` | Pure parsers for the standard Bluetooth SIG characteristics. |

## Scope

| Data | Supported | Source |
|------|-----------|--------|
| Presence | ✅ | BLE advertisement |
| Manufacturer / hardware / firmware | ✅ | Device Information Service `0x180A` |
| Battery % | ⚠️ | Battery Service `0x180F` — only if the device exposes it (the iGS10S does not) |
| Speed / distance / ride data | ❌ | proprietary authenticated sync (not exposed over BLE) |

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Credits

Built to back the [`ha-igps-ble`](https://github.com/hudsonbrendon/ha-igps-ble)
Home Assistant integration. Author [@hudsonbrendon](https://github.com/hudsonbrendon).

## License

MIT — see [LICENSE](LICENSE).
