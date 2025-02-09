__all__ = [
    "HubspaceError",
    "InvalidAuth",
    "InvalidResponse",
    "HubspaceDevice",
    "HubspaceState",
    "get_hs_device",
    "anonymize_device",
    "anonymize_devices",
    "v1",
    "EventType",
]


from importlib.metadata import PackageNotFoundError, version

try:
    # Change here if project is renamed and does not equal the package name
    dist_name = "aiohubspace"
    __version__ = version(dist_name)
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"
finally:
    del version, PackageNotFoundError


from . import v1
from .anonomyize_data import anonymize_device, anonymize_devices
from .device import HubspaceDevice, HubspaceState, get_hs_device
from .errors import HubspaceError, InvalidAuth, InvalidResponse
from .types import EventType
