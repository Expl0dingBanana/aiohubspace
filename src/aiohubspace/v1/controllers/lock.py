"""Controller holding and managing Hubspace resources of type `lock`."""

from ...device import HubspaceDevice
from ..models import features
from ..models.lock import Lock, LockPut
from ..models.resource import DeviceInformation, ResourceTypes
from .base import BaseResourcesController


class LockController(BaseResourcesController[Lock]):
    """Controller holding and managing Hubspace resources of type `lock`."""

    ITEM_TYPE_ID = ResourceTypes.DEVICE
    ITEM_TYPES = [ResourceTypes.LOCK]
    ITEM_CLS = Lock
    ITEM_MAPPING = {"position": "lock-control"}

    async def lock(self, device_id: str) -> None:
        """Engage the lock"""
        await self.set_state(
            device_id, lock_position=features.CurrentPositionEnum.LOCKING
        )

    async def unlock(self, device_id: str) -> None:
        """Disengage the lock"""
        await self.set_state(
            device_id, lock_position=features.CurrentPositionEnum.UNLOCKING
        )

    async def initialize_elem(self, hs_device: HubspaceDevice) -> Lock:
        """Initialize the element"""
        available: bool = False
        current_position: features.CurrentPositionFeature | None = None
        for state in hs_device.states:
            if state.functionClass == "lock-control":
                current_position = features.CurrentPositionFeature(
                    position=features.CurrentPositionEnum(state.value)
                )
            elif state.functionClass == "available":
                available = state.value

        self._items[hs_device.id] = Lock(
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
            position=current_position,
        )
        return self._items[hs_device.id]

    async def update_elem(self, hs_device: HubspaceDevice) -> set:

        cur_item = self.get_device(hs_device.id)
        updated_keys = set()
        for state in hs_device.states:
            if state.functionClass == "lock-control":
                new_val = features.CurrentPositionEnum(state.value)
                if cur_item.position.position != new_val:
                    updated_keys.add("position")
                cur_item.position.position = features.CurrentPositionEnum(state.value)
            elif state.functionClass == "available":
                if cur_item.available != state.value:
                    updated_keys.add("available")
                cur_item.available = state.value
        return updated_keys

    async def set_state(
        self,
        device_id: str,
        lock_position: features.CurrentPositionEnum | None = None,
    ) -> None:
        """Set supported feature(s) to fan resource."""
        update_obj = LockPut()
        if lock_position is not None:
            update_obj.position = features.CurrentPositionFeature(
                position=lock_position
            )
        await self.update(device_id, obj_in=update_obj)
