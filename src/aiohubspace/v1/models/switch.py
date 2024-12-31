from dataclasses import dataclass, field

from ..models import features
from .resource import DeviceInformation, ResourceTypes


@dataclass
class Switch:
    """Representation of a HubSpace Switch"""

    id: str  # ID used when interacting with HubSpace
    available: bool

    on: dict[str, features.OnFeature]
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
class SwitchPut:
    """States that can be updated for a Switch"""

    on: dict[str, features.OnFeature] | None = None