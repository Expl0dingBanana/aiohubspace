__all__ = [
    "HubspaceDevice",
    "HubspaceState",
    "get_hs_device",
]
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class HubspaceState:
    """State of a given function

    :param functionClass: Function class for the state (ie, power)
    :param value: Value to set for the function_class
    :param lastUpdateTime: Last time the state was updated (in epoch ms).
    :param functionInstance: Additional information about the function (ie, light-power).
        Default: None
    """

    functionClass: str
    value: Any
    lastUpdateTime: Optional[int] = None
    functionInstance: Optional[str] = None


@dataclass
class HubspaceDevice:
    id: str
    device_id: str
    model: str
    device_class: str
    default_name: str
    default_image: str
    friendly_name: str
    functions: list[dict] = field(default=list)
    states: list[HubspaceState] = field(default=list)
    children: list[str] = field(default=list)
    manufacturerName: Optional[str] = field(default=None)

    def __hash__(self):
        return hash((self.id, self.friendly_name))

    def __post_init__(self):
        # Dimmer Switch fix - A switch cannot dim, but a light can
        if self.device_class == "switch" and any(
            [state.functionClass == "brightness" for state in self.states]
        ):
            self.device_class = "light"
        # Fix exhaust fans
        if self.device_class == "exhaust-fan":
            if self.default_image == "fan-exhaust-icon":
                self.model = "BF1112"
        # Fix fans
        if self.device_class in ["fan", "ceiling-fan"]:
            if not self.model and self.default_image == "ceiling-fan-snyder-park-icon":
                self.model = "Driskol"
            elif not self.model and self.default_image == "ceiling-fan-vinings-icon":
                self.model = "Vinwood"
            elif (
                self.model == "TBD" and self.default_image == "ceiling-fan-chandra-icon"
            ):
                self.model = "Zandra"
            elif (
                self.model == "TBD"
                and self.default_image == "ceiling-fan-ac-cct-dardanus-icon"
            ):
                self.model = "Nevali"
            elif not self.model and self.default_image == "ceiling-fan-slender-icon":
                self.model = "Tager"
        # Fix lights
        elif self.device_class == "light":
            if self.default_image == "a19-e26-color-cct-60w-smd-frosted-icon":
                self.model = "12A19060WRGBWH2"
            elif self.default_image == "slide-dimmer-icon":
                self.model = "HPDA110NWBP"
        # Fix locks
        elif self.device_class == "lock":
            pass
        # Fix switches
        elif self.device_class == "switch":
            if self.default_image == "smart-switch-icon" and self.model == "TBD":
                self.model = "HPSA11CWB"
        # Fix valves
        elif self.device_class == "valve":
            pass
        # Fix glass doors - Treat as a switch
        elif self.device_class == "glass-door":
            self.device_class = "switch"
            self.manufacturerName = "Feather River Doors"


def get_hs_device(hs_device: dict[str, Any]) -> HubspaceDevice:
    """Convert the Hubspace device definition into a HubspaceDevice"""
    description = hs_device.get("description", {})
    device = description.get("device", {})
    processed_states: list[HubspaceState] = []
    for state in hs_device.get("state", {}).get("values", []):
        processed_states.append(
            HubspaceState(
                functionClass=state.get("functionClass"),
                value=state.get("value"),
                lastUpdateTime=state.get("lastUpdateTime"),
                functionInstance=state.get("functionInstance"),
            )
        )
    dev_dict = {
        "id": hs_device.get("id"),
        "device_id": hs_device.get("deviceId"),
        "model": device.get("model"),
        "device_class": device.get("deviceClass"),
        "default_name": device.get("defaultName"),
        "default_image": description.get("defaultImage"),
        "friendly_name": hs_device.get("friendlyName"),
        "functions": description.get("functions", []),
        "states": processed_states,
        "children": hs_device.get("children", []),
        "manufacturerName": device.get("manufacturerName"),
    }
    return HubspaceDevice(**dev_dict)


def get_function_from_device(
    hs_device: HubspaceDevice, function_class: str, function_instance
) -> dict:
    for func in hs_device.functions:
        if func.get("functionClass") != function_class:
            continue
        if func.get("functionInstance") != function_instance:
            continue
        return func
    return None