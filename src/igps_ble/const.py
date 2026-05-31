"""UUIDs Bluetooth SIG e defaults do iGPSPORT iGS10S.

UUIDs confirmados no recon (docs/RECON_FINDINGS.md). Ajuste NAME_PREFIXES
para o local_name exato observado na Task 1.
"""

# Battery Service / characteristic (Bluetooth SIG).
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# Device Information Service / characteristics (Bluetooth SIG).
DEVICE_INFO_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
MANUFACTURER_NAME_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

# Prefixos de local_name usados pra reconhecer o aparelho no advertisement.
# Confirme/ajuste com o que a Task 1 observou.
NAME_PREFIXES = ("iGS10S", "iGPSPORT", "iGS")

MANUFACTURER = "iGPSPORT"
DEFAULT_MODEL = "iGS10S"
