<p align="center">
  <img src="assets/igpsport-logo.png" alt="iGPSPORT" width="420">
</p>

# python-igps-ble

[![CI](https://github.com/hudsonbrendon/python-igps-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/hudsonbrendon/python-igps-ble/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/python-igps-ble)](https://pypi.org/project/python-igps-ble/)
[![Python](https://img.shields.io/pypi/pyversions/python-igps-ble)](https://pypi.org/project/python-igps-ble/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Talk to an **iGPSPORT iGS10S** cycling computer over Bluetooth LE from Python —
battery, internal sensors, ride status, stored activities, last GPS position and
the rider/bike profile, through iGPSPORT's proprietary protobuf-over-Nordic-UART
protocol (reverse engineered from the official app, no pairing or login needed).

This library powers the
[**iGPSPORT iGS10S Home Assistant integration**](https://github.com/hudsonbrendon/ha-igps-ble),
but works standalone in any async Python project (or straight from the command line).

> Protocol notes:
> [`ha-igps-ble/docs/PROTOCOL.md`](https://github.com/hudsonbrendon/ha-igps-ble/blob/main/docs/PROTOCOL.md).

## Features

- 🔌 **Async BLE control** built on [`bleak`](https://github.com/hbldh/bleak) —
  works on Linux, macOS, and Windows.
- 🔍 **Discovery helper** — `discover_devices()` finds nearby iGPSPORT devices
  (presence + RSSI).
- 🏷️ **Device info** — manufacturer, hardware revision, firmware, serial and
  protocol version.
- 🔋 **Battery** — level (%) and voltage.
- 🌡️ **Sensors** — internal temperature, free memory, device clock.
- 🚴 **Ride status** — idle / recording / paused, live ride fields while recording,
  last GPS position.
- 🗂️ **Activities** — list of rides stored on the device (start time, size).
- ⚙️ **Profile** — write rider weight/height/age/sex, wheel circumference, bike
  weight and time zone (`set_profile`).
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
igps-ble info AA:BB:CC:DD:EE:FF     # connect and read everything
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
| `read_state(client, address, name, rssi, session=None)` | Read everything over an already-connected `BleakClient`. |
| `IGPSSession(client)` | Request/response over the NUS channels; `await session.start()` once per connection. |
| `set_profile(session, UserProfile(...))` | Write the whole rider/bike profile (the device does not report it back). |
| `IGPSDeviceState` | Frozen dataclass with everything read (battery, sensors, ride status, GPS, activities…). |
| `igps_ble.protocol` | Framing (20-byte header, CRC-8/MAXIM) and a tiny protobuf codec. |
| `parse_battery_level(data)` / `decode_device_string(data)` | Pure parsers for the standard Bluetooth SIG characteristics. |

## Scope

| Data | Supported | Source |
|------|-----------|--------|
| Presence | ✅ | BLE advertisement |
| Manufacturer / hardware / firmware | ✅ | Device Information Service `0x180A` |
| Battery % / voltage | ✅ | FACTORY service (protobuf) |
| Serial, memory, temperature, clock | ✅ | FACTORY service |
| Ride status, last GPS fix, live ride fields | ✅ | DEV_STATUS service (live field units unconfirmed) |
| Stored activity list | ✅ | CYCLING_DATA service |
| Rider/bike profile, time zone | ✅ write-only | USER_CONFIG service |
| `.fit` download, display/page settings, time sync | ❌ | not implemented / unsupported by the iGS10S firmware |

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
