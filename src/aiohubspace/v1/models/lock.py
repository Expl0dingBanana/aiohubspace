from dataclasses import dataclass, field

from ..models import features
from .resource import DeviceInformation, ResourceTypes


@dataclass
class Lock:
    """Representation of a HubSpace Lock"""

    id: str  # ID used when interacting with HubSpace
    available: bool

    position: features.CurrentPositionFeature
    # Defined at initialization
    instances: dict = field(default_factory=lambda: dict(), repr=False, init=False)
    device_information: DeviceInformation = field(default_factory=DeviceInformation)

    type: ResourceTypes = ResourceTypes.FAN

    def __init__(self, functions: list, **kwargs):
        for key, value in kwargs.items():
            if key == "instances":
                continue
            setattr(self, key, value)
        instances = {}
        for function in functions:
            try:
                if function["functionInstance"]:
                    instances[function["functionClass"]] = function["functionInstance"]
            except KeyError:
                continue
        self.instances = instances

    def get_instance(self, elem):
        """Lookup the instance associated with the elem"""
        return self.instances.get(elem, None)


@dataclass
class LockPut:
    """States that can be updated for a Lock"""

    position: features.CurrentPositionFeature | None = None