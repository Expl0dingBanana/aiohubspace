"""Controller holding and managing Hubspace resources of type `switch`."""

from ... import errors
from ...device import HubspaceDevice
from ..models import features
from ..models.resource import DeviceInformation, ResourceTypes
from ..models.switch import Switch, SwitchPut
from .base import BaseResourcesController


class SwitchController(BaseResourcesController[Switch]):
    """Controller holding and managing Hubspace resources of type `switch`.

    A switch can have one or more toggleable elements. They are controlled
    by their functionInstance.
    """

    ITEM_TYPE_ID = ResourceTypes.DEVICE
    ITEM_TYPES = [
        ResourceTypes.SWITCH,
        ResourceTypes.POWER_OUTLET,
        ResourceTypes.LANDSCAPE_TRANSFORMER,
    ]
    ITEM_CLS = Switch
    ITEM_MAPPING = {}

    async def turn_on(self, device_id: str, instance: str | None = None) -> None:
        """Turn on the switch."""
        await self.set_state(device_id, on=True, instance=instance)

    async def turn_off(self, device_id: str, instance: str | None = None) -> None:
        """Turn off the switch."""
        await self.set_state(device_id, on=False, instance=instance)

    async def initialize_elem(self, hs_device: HubspaceDevice) -> Switch:
        """Initialize the element"""
        available: bool = False
        on: dict[str, features.OnFeature] = {}
        for state in hs_device.states:
            if state.functionClass in ["power", "toggle"]:
                on[state.functionInstance] = features.OnFeature(
                    on=state.value == "on",
                    func_class=state.functionClass,
                    func_instance=state.functionInstance,
                )
            elif state.functionClass == "available":
                available = state.value

        self._items[hs_device.id] = Switch(
            hs_device.functions,
            id=hs_device.id,
            available=available,
            device_information=DeviceInformation(
                device_class=hs_device.device_class,
                default_image=hs_device.default_image,
                default_name=hs_device.default_name,
                manufacturer=hs_device.manufacturerName,
                model=hs_device.model,
                name=hs_device.friendly_name,
                parent_id=hs_device.device_id,
            ),
            on=on,
        )
        return self._items[hs_device.id]

    async def update_elem(self, hs_device: HubspaceDevice) -> set:
        cur_item = self.get_device(hs_device.id)
        updated_keys = set()
        for state in hs_device.states:
            if state.functionClass in ["power", "toggle"]:
                new_val = state.value == "on"
                if cur_item.on[state.functionInstance].on != new_val:
                    updated_keys.add("on")
                cur_item.on[state.functionInstance].on = state.value == "on"
            elif state.functionClass == "available":
                if cur_item.available != state.value:
                    updated_keys.add("available")
                cur_item.available = state.value
        return updated_keys

    async def set_state(
        self,
        device_id: str,
        on: bool | None = None,
        instance: str | None = None,
    ) -> None:
        """Set supported feature(s) to fan resource."""
        update_obj = SwitchPut()
        try:
            cur_item = self.get_device(device_id)
        except errors.DeviceNotFound:
            self._logger.info("Unable to find device %s", device_id)
            return
        if on is not None:
            try:
                update_obj.on = features.OnFeature(
                    on=on,
                    func_class=cur_item.on[instance].func_class,
                    func_instance=instance,
                )
            except KeyError:
                self._logger.info("Unable to find instance %s", instance)
        await self.update(device_id, obj_in=update_obj)
