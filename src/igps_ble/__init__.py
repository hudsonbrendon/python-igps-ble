"""Pure-Python BLE library for the iGPSPORT iGS10S cycling computer."""

from .client import IGPSClient, IGPSCommandError, IGPSSession, read_state, set_profile
from .models import Activity, IGPSDeviceState, UserProfile

__version__ = "0.3.2"

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
