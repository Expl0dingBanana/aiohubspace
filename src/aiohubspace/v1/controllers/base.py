import asyncio
import copy
import time
from asyncio.coroutines import iscoroutinefunction
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Callable, Generic, Iterator, TypeVar

from aiohubspace.errors import DeviceNotFound, ExceededMaximumRetries

from .. import v1_const
from ..device import HubspaceDevice, get_hs_device
from ..models.resource import ResourceTypes
from .event import EventCallBackType, EventType, HubspaceEvent

if TYPE_CHECKING:
    from .. import HubspaceBridgeV1


EventSubscriptionType = tuple[
    EventCallBackType,
    "tuple[EventType] | None",
]

ID_FILTER_ALL = "*"

HubspaceResource = TypeVar("HubspaceResource")


class BaseResourcesController(Generic[HubspaceResource]):
    """Base Controller for Hubspace devices"""

    ITEM_TYPE_ID: ResourceTypes | None = None
    ITEM_TYPES: list[ResourceTypes] | None = None
    ITEM_CLS = None
    ITEM_MAPPING: dict = {}

    def __init__(self, bridge: "HubspaceBridgeV1") -> None:
        """Initialize instance."""
        self._bridge = bridge
        self._items: dict[str, HubspaceResource] = {}
        self._logger = bridge.logger.getChild(self.ITEM_CLS.__name__)
        self._subscribers: dict[str, EventSubscriptionType] = {ID_FILTER_ALL: []}
        self._initialized: bool = False
        self._item_values = [x.value for x in self.ITEM_TYPES]

    def __getitem__(self, device_id: str) -> HubspaceResource:
        """Get item by device_id."""
        return self._items[device_id]

    def __iter__(self) -> Iterator[HubspaceResource]:
        """Iterate items."""
        return iter(self._items.values())

    def __contains__(self, device_id: str) -> bool:
        """Return bool if device_id is in items."""
        return device_id in self._items

    @property
    def items(self) -> list[HubspaceResource]:
        """Return all items for this resource."""
        return list(self._items.values())

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def _handle_event(
        self, evt_type: EventType, evt_data: HubspaceEvent | None
    ) -> None:
        """Handle incoming event for this resource"""
        if evt_data is None:
            return
        item_id = evt_data.get("device_id", None)
        if evt_type == EventType.RESOURCE_ADDED:
            cur_item = await self.initialize_elem(evt_data["device"])
            self._bridge.add_device(evt_data["device"].id)
        elif evt_type == EventType.RESOURCE_DELETED:
            cur_item = self._items.pop(item_id, evt_data)
            self._bridge.remove_device(evt_data["device_id"])
        elif evt_type == EventType.RESOURCE_UPDATED:
            # existing item updated
            try:
                cur_item = self.get_device(item_id)
            except DeviceNotFound:
                cur_item = None
            if cur_item is None:
                return
            # @TODO - Check for changes rather than issuing a full update for everything each time
            await self.update_elem(evt_data["device"])
        else:
            # Skip all other events
            return
        subscribers = (
            self._subscribers.get(item_id, []) + self._subscribers[ID_FILTER_ALL]
        )
        for callback, event_filter in subscribers:
            if event_filter is not None and evt_type not in event_filter:
                continue
            # dispatch the full resource object to the callback
            if iscoroutinefunction(callback):
                asyncio.create_task(callback(evt_type, cur_item))
            else:
                callback(evt_type, cur_item)

    async def initialize(self, initial_data: list[dict]) -> None:
        """Initialize controller by fetching all items for this resource type from bridge."""
        if self._initialized:
            return
        valid_devices: list[HubspaceDevice] = []
        try:
            valid_devices = self.get_filtered_devices(initial_data)
        except AttributeError:
            for element in initial_data:
                if element["typeId"] != self.ITEM_TYPE_ID.value:
                    self._logger.debug(
                        "TypeID [%s] does not match %s",
                        element["typeId"],
                        self.ITEM_TYPE_ID.value,
                    )
                    continue
                device = get_hs_device(element)
                if device.device_class not in self._item_values:
                    self._logger.debug(
                        "Device Class [%s] is not contained in %s",
                        device.device_class,
                        self._item_values,
                    )
                    continue
                valid_devices.append(device)

        for item in valid_devices:
            await self._handle_event(
                EventType.RESOURCE_ADDED,
                HubspaceEvent(
                    type=EventType.RESOURCE_ADDED,
                    device_id=item.device_id,
                    device=item,
                ),
            )
        # subscribe to item updates
        res_filter = tuple(x.value for x in self.ITEM_TYPES)
        if res_filter:
            self._bridge.events.subscribe(
                self._handle_event,
                resource_filter=res_filter,
            )
        else:
            # Subscribe to all events
            self._bridge.events.subscribe(
                self._handle_event,
            )
        self._initialized = True

    async def initialize_elem(self, element: HubspaceDevice) -> None:
        raise NotImplementedError("Class should implement initialize_elem")

    async def update_elem(self, element: HubspaceDevice) -> None:
        raise NotImplementedError("Class should implement update_elem")

    def subscribe(
        self,
        callback: EventCallBackType,
        id_filter: str | tuple[str] | None = None,
        event_filter: EventType | tuple[EventType] | None = None,
    ) -> Callable:
        """
        Subscribe to status changes for this resource type.

        Parameters:
            - `callback` - callback function to call when an event emits.
            - `id_filter` - Optionally provide resource ID(s) to filter events for.
            - `event_filter` - Optionally provide EventType(s) as filter.

        Returns:
            function to unsubscribe.
        """
        if not isinstance(event_filter, None | list | tuple):
            event_filter = (event_filter,)

        if id_filter is None:
            id_filter = (ID_FILTER_ALL,)
        elif not isinstance(id_filter, list | tuple):
            id_filter = (id_filter,)

        subscription = (callback, event_filter)

        for id_key in id_filter:
            if id_key not in self._subscribers:
                self._subscribers[id_key] = []
            self._subscribers[id_key].append(subscription)

        # unsubscribe logic
        def unsubscribe():
            for id_key in id_filter:
                if id_key not in self._subscribers:
                    continue
                self._subscribers[id_key].remove(subscription)

        return unsubscribe

    async def update(
        self,
        device_id: str,
        obj_in: Generic[HubspaceResource],
    ) -> None:
        """Update Hubspace with the new data

        :param device_id: Hubspace Device ID
        :param obj_in: Hubspace Resource elements to change
        """
        cur_item = self._items.get(device_id)
        if cur_item is None:
            return
        hs_states = dataclass_to_hs(cur_item, obj_in, self.ITEM_MAPPING)
        if not hs_states:
            self._logger.debug("No states to send. Skipping")
            return
        # Make a clone if the update fails
        fallback = copy.deepcopy(cur_item)
        # Update the state of the item to match the new states
        update_dataclass(cur_item, obj_in)
        # If the update fails, restore the old states
        fallback_required: bool = False
        # @TODO - Implement bluetooth logic for update
        if True:
            url = v1_const.HUBSPACE_DEVICE_STATE.format(
                self._bridge.account_id, str(device_id)
            )
            headers = {
                "host": v1_const.HUBSPACE_DATA_HOST,
                "content-type": "application/json; charset=utf-8",
            }
            payload = {"metadeviceId": str(device_id), "values": hs_states}
            try:
                res = await self._bridge.request(
                    "put", url, json=payload, headers=headers
                )
            except ExceededMaximumRetries:
                fallback_required = True
            else:
                # Bad states provided
                if res.status == 400:
                    self._logger.warning(
                        "Invalid update provided for %s using %s", device_id, hs_states
                    )
                    fallback_required = True
        if fallback_required:
            self._items[device_id] = fallback

    def get_device(self, device_id) -> HubspaceResource:
        cur_item = self._items.get(device_id)
        if cur_item is None:
            raise DeviceNotFound(device_id)
        return cur_item


def update_dataclass(elem: HubspaceResource, cls: dataclass):
    """Updates the element with the latest changes"""
    for f in fields(cls):
        cur_val = getattr(cls, f.name, None)
        elem_val = getattr(elem, f.name)
        if cur_val is None:
            continue
        # Special processing for dicts
        if isinstance(elem_val, dict):
            cur_val = {getattr(cur_val, "func_instance", None): cur_val}
            getattr(elem, f.name).update(cur_val)
        else:
            setattr(elem, f.name, cur_val)


def dataclass_to_hs(
    elem: HubspaceResource, cls: dataclass, mapping: dict
) -> list[dict]:
    """Convert the current state to be consumed by Hubspace"""
    states = []
    for f in fields(cls):
        cur_val = getattr(cls, f.name, None)
        if cur_val is None:
            continue
        if cur_val == getattr(elem, f.name, None):
            continue
        hs_key = mapping.get(f.name, f.name)
        new_val = cur_val.hs_value
        if not isinstance(new_val, list):
            new_val = [new_val]
        for val in new_val:
            new_state = {
                "functionClass": hs_key,
                "functionInstance": elem.get_instance(hs_key),
                "lastUpdateTime": int(time.time()),
                "value": None,
            }
            if isinstance(val, dict):
                new_state.update(val)
            else:
                new_state["value"] = val
            states.append(new_state)
    return states
