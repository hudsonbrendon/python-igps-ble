# python-igps-ble

Pure-Python BLE library for the **iGPSPORT iGS10S** cycling computer.

Reads, over standard Bluetooth Low Energy, what the device exposes to
third parties: **presence**, **battery level**, and **device info**
(model / firmware / manufacturer). The proprietary `.fit` sync used by the
official iGPSPORT app is **out of scope** (see `ha-igps-ble/docs/PROTOCOL.md`).

> Built to back the [`ha-igps-ble`](https://github.com/hudsonbrendon/ha-igps-ble)
> Home Assistant integration, but usable standalone.

## Install

```bash
pip install python-igps-ble
```

## CLI

```bash
igps-ble scan                 # procura aparelhos iGPSPORT por perto
igps-ble info AA:BB:CC:DD:EE:FF   # bateria + device-info
```

## Uso programático

```python
import asyncio
from igps_ble import IGPSDeviceState
from igps_ble.scanner import discover_devices
from igps_ble.client import IGPSClient

async def main():
    for dev in await discover_devices(timeout=10):
        state: IGPSDeviceState = await IGPSClient(dev.address, dev.name).async_read_state()
        print(state)

asyncio.run(main())
```

## Escopo

| Dado | Suportado | Fonte |
|------|-----------|-------|
| Presença | ✅ | advertisement BLE |
| Bateria % | ✅* | Battery Service `0x180F` |
| Modelo / firmware | ✅* | Device Information `0x180A` |
| Velocidade / distância / pedalada | ❌ | sync proprietário (não exposto por BLE) |

\* depende de o iGS10S expor o serviço SIG correspondente — confirmado por recon.

## Desenvolvimento

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Licença

MIT
