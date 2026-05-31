"""CLI: `igps-ble scan` e `igps-ble info <ADDRESS>`."""

from __future__ import annotations

import argparse
import asyncio

from .client import IGPSClient
from .scanner import discover_devices


async def _scan(timeout: float) -> None:
    devices = await discover_devices(timeout=timeout)
    if not devices:
        print("Nenhum iGPSPORT encontrado. Ligue o aparelho e aproxime.")
        return
    for d in devices:
        print(f"{d.address}  rssi={d.rssi}  name={d.name}")


async def _info(address: str) -> None:
    state = await IGPSClient(address).async_read_state()
    print(f"Endereço:     {state.address}")
    print(f"Modelo:       {state.model}")
    print(f"Firmware:     {state.firmware}")
    print(f"Fabricante:   {state.manufacturer}")
    print(f"Bateria:      {state.battery_level}%")


def main() -> None:
    parser = argparse.ArgumentParser(prog="igps-ble")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_scan = sub.add_parser("scan", help="Procura aparelhos iGPSPORT por perto")
    p_scan.add_argument("--timeout", type=float, default=10.0)
    p_info = sub.add_parser("info", help="Conecta e lê bateria/device-info")
    p_info.add_argument("address")

    args = parser.parse_args()
    if args.cmd == "scan":
        asyncio.run(_scan(args.timeout))
    elif args.cmd == "info":
        asyncio.run(_info(args.address))


if __name__ == "__main__":
    main()
