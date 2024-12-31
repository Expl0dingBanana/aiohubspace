"""Generic/base Resource Model(s)."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ResourceTypes(Enum):
    """
    Type of the supported resources
    """

    DEVICE = "metadevice.device"
    HOME = "metadata.home"
    ROOM = "metadata.room"
    FAN = "fan"
    LANDSCAPE_TRANSFORMER = "landscape-transformer"
    LIGHT = "light"
    LOCK = "lock"
    POWER_OUTLET = "power-outlet"
    SWITCH = "switch"
    UNKNOWN = "unknown"
    WATER_TIMER = "water-timer"

    @classmethod
    def _missing_(cls: type, value: object):  # noqa: ARG003
        """Set default enum member if an unknown value is provided."""
        return ResourceTypes.UNKNOWN


@dataclass
class DeviceInformation:

    device_class: Optional[str] = None
    default_image: Optional[str] = None
    default_name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    name: Optional[str] = None
    parent_id: Optional[str] = None