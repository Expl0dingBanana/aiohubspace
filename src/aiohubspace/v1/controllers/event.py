"""Handle connecting to the HUE Eventstream and distribute events."""

import asyncio
from asyncio.coroutines import iscoroutinefunction
from collections.abc import Callable
from enum import Enum
from types import NoneType
from typing import TYPE_CHECKING, NotRequired, TypedDict

from aiohttp.client_exceptions import ClientError

from ..device import HubspaceDevice, get_hs_device

if TYPE_CHECKING:
    from .. import HubSpaceBridgeV1


class EventStreamStatus(Enum):
    """Status options of EventStream."""

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class EventType(Enum):
    """Enum with possible Events."""

    # resource events match those emitted by Hue eventstream
    RESOURCE_ADDED = "add"
    RESOURCE_UPDATED = "update"
    RESOURCE_DELETED = "delete"
    # connection events emitted by (this) events controller
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTED = "reconnected"


class HubSpaceEvent(TypedDict):
    """Hue Event message as emitted by the EventStream."""

    type: EventType  # = EventType (add, update, delete)
    device_id: str  # ID for interacting with the device
    device: NotRequired[HubspaceDevice]  # HubSpace Device


EventCallBackType = Callable[[EventType, dict | None], None]
EventSubscriptionType = tuple[
    EventCallBackType,
    "tuple[EventType] | None",
    "tuple[ResourceTypes] | None",
]


class EventStream:
    """Holds the connection to the HUE Clip EventStream."""

    def __init__(self, bridge: "HubSpaceBridgeV1", polling_interval: int) -> None:
        """Initialize instance."""
        self._bridge = bridge
        self._listeners = set()
        self._event_queue = asyncio.Queue()
        self._status = EventStreamStatus.DISCONNECTED
        self._bg_tasks: list[asyncio.Task] = []
        self._subscribers: list[EventSubscriptionType] = []
        self._logger = bridge.logger.getChild("events")
        self._polling_interval: int = polling_interval

    @property
    def connected(self) -> bool:
        """Return bool if we're connected."""
        return self._status == EventStreamStatus.CONNECTED

    @property
    def status(self) -> EventStreamStatus:
        """Return connection status."""
        return self._status

    @property
    def polling_interval(self) -> int:
        return self._polling_interval

    @polling_interval.setter
    def polling_interval(self, polling_interval: int) -> None:
        self._polling_interval = polling_interval

    async def initialize(self) -> None:
        """Start the polling processes"""
        assert len(self._bg_tasks) == 0
        self._bg_tasks.append(asyncio.create_task(self.__event_reader()))
        self._bg_tasks.append(asyncio.create_task(self.__event_processor()))

    async def stop(self) -> None:
        """Stop listening for events."""
        for task in self._bg_tasks:
            task.cancel()
        self._bg_tasks = []

    def subscribe(
        self,
        callback: EventCallBackType,
        event_filter: EventType | tuple[EventType] | None = None,
        resource_filter: tuple[str] | None = None,
    ) -> Callable:
        """
        Subscribe to events emitted

        Parameters:
            - `callback` - callback function to call when an event emits.
            - `event_filter` - Optionally provide an EventType as filter.
            - `resource_filter` - Optionally provide a ResourceType as filter.

        Returns:
            function to unsubscribe.
        """
        if not isinstance(event_filter, NoneType | tuple):
            event_filter = (event_filter,)
        # if not isinstance(resource_filter, NoneType | tuple):
        #     resource_filter = (resource_filter,)
        subscription = (callback, event_filter, resource_filter)

        def unsubscribe():
            self._subscribers.remove(subscription)

        self._subscribers.append(subscription)
        return unsubscribe

    def emit(self, event_type: EventType, data: HubSpaceEvent = None) -> None:
        """Emit event to all listeners."""
        for callback, event_filter, resource_filter in self._subscribers:
            if event_filter is not None and event_type not in event_filter:
                continue
            if data is not None:
                if resource_filter is not None:
                    if (
                        "device" in data
                        and data["device"]
                        and data["device"].device_class not in resource_filter
                    ):
                        continue
            if iscoroutinefunction(callback):
                asyncio.create_task(callback(event_type, data))
            else:
                callback(event_type, data)

    async def __event_reader(self) -> None:
        """Poll the current states"""
        self._status = EventStreamStatus.CONNECTING
        while True:
            processed_ids = []
            skipped_ids = []
            try:
                data = await self._bridge.fetch_data()
                for dev in data:
                    hs_dev = get_hs_device(dev)
                    event_type = EventType.RESOURCE_UPDATED
                    if hs_dev.id not in self._bridge.tracked_devices:
                        event_type = EventType.RESOURCE_ADDED
                        self._bridge.add_device(hs_dev.id)
                    if hs_dev.device_class not in self._bridge.tracked_device_classes:
                        skipped_ids.append(hs_dev.id)
                        continue
                    self._event_queue.put_nowait(
                        HubSpaceEvent(
                            type=event_type,
                            device_id=hs_dev.id,
                            device=hs_dev,
                        )
                    )
                    processed_ids.append(hs_dev.id)
            except (ClientError, asyncio.TimeoutError) as err:
                # Auto-retry will take care of the issue
                self._logger.warning(err)
            except Exception as err:
                self._logger.warning(err)
                raise err
            else:
                # Connection was successful. Find missing devices
                for dev_id in self._bridge.tracked_devices:
                    if dev_id not in processed_ids + skipped_ids:
                        self._event_queue.put_nowait(
                            HubSpaceEvent(
                                type=EventType.RESOURCE_DELETED, device_id=dev_id
                            )
                        )
                        self._bridge.remove_device(dev_id)
            self._status = EventStreamStatus.DISCONNECTED
            await asyncio.sleep(self._polling_interval)

    async def __event_processor(self) -> None:
        """Process the hubspace devices"""
        while True:
            event: HubSpaceEvent = await self._event_queue.get()
            self.emit(event["type"], event)