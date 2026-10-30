"""Pure-Python BLE library for the iGPSPORT iGS10S cycling computer."""

from importlib import metadata

from .client import IGPSClient, IGPSCommandError, IGPSSession, read_state, set_profile
from .models import Activity, IGPSDeviceState, UserProfile

try:
    __version__ = metadata.version("python-igps-ble")
except metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "Activity",
    "IGPSClient",
    "IGPSCommandError",
    "IGPSDeviceState",
    "IGPSSession",
    "UserProfile",
    "__version__",
    "read_state",
    "set_profile",
]
