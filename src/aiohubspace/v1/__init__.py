"""Controls HubSpace devices on v1 API"""

__all__ = ["HubSpaceBridgeV1", "InvalidAuth", "InvalidResponse", "HubspaceError"]

import asyncio
import copy
import logging
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, Callable, Generator, Optional

import aiohttp
from aiohttp import web_exceptions

from . import v1_const
from .auth import HubSpaceAuth
from .controllers.device import DeviceController
from .controllers.event import EventCallBackType, EventStream
from .controllers.fan import FanController
from .controllers.light import LightController
from .controllers.lock import LockController
from .controllers.switch import SwitchController
from .controllers.valve import ValveController
from .errors import ExceededMaximumRetries, HubspaceError, InvalidAuth, InvalidResponse


class HubSpaceBridgeV1:
    """Controls HubSpace devices on v1 API"""

    _web_session: Optional[aiohttp.ClientSession] = None

    def __init__(
        self,
        username: str,
        password: str,
        session: Optional[aiohttp.ClientSession] = None,
        polling_interval: int = 30,
    ):
        self._web_session: aiohttp.ClientSession = session
        self._account_id: Optional[str] = None
        self._auth = HubSpaceAuth(username, password)
        self.logger = logging.getLogger(f"{__package__}[{username}]")
        self.logger.addHandler(logging.StreamHandler())
        self.logger.setLevel(logging.DEBUG)
        self._known_devs: set[str] = set()
        self._known_dev_classes = {}
        # Data Updater
        self._events: EventStream = EventStream(self, polling_interval)
        # Data Controllers
        self._binary_sensors = None
        self._devices: DeviceController = DeviceController(self)
        self._fans: FanController = FanController(self)
        self._lights: LightController = LightController(self)
        self._locks: LockController = LockController(self)
        self._sensors = None
        self._switches: SwitchController = SwitchController(self)
        self._valves: ValveController = ValveController(self)

    async def __aenter__(self) -> "HubSpaceBridgeV1":
        """Return Context manager."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> bool | None:
        """Exit context manager."""
        await self.close()
        if exc_val:
            raise exc_val
        return exc_type

    @property
    def binary_sensors(self) -> None:
        return self._binary_sensors

    @property
    def devices(self) -> DeviceController:
        return self._devices

    @property
    def events(self) -> EventStream:
        return self._events

    @property
    def fans(self) -> FanController:
        return self._fans

    @property
    def lights(self) -> LightController:
        return self._lights

    @property
    def locks(self) -> LockController:
        return self._locks

    @property
    def sensors(self) -> None:
        return self._sensors

    @property
    def switches(self) -> SwitchController:
        return self._switches

    @property
    def valves(self) -> ValveController:
        return self._valves

    @property
    def _controllers(self) -> set:
        dev_controllers = {
            # self._binary_sensors,
            self._devices,
            self._fans,
            self._lights,
            self._locks,
            # self._sensors,
            self._switches,
            self._valves,
        }
        return dev_controllers

    @property
    def controllers(self) -> set:
        initialized = set()
        for controller in self._controllers:
            if controller and controller.initialized:
                initialized.add(controller)
        return initialized

    @property
    def tracked_devices(self) -> set:
        if not self._known_devs:
            for controller in self.controllers:
                for device in controller.items:
                    self._known_devs.add(device.id)
        return self._known_devs

    @property
    def tracked_device_classes(self) -> set:
        dev_classes = set()
        for tracked_dc in self.device_classes.values():
            for cls in tracked_dc:
                dev_classes.add(cls)
        return dev_classes

    @property
    def device_classes(self) -> dict[str, list[str]]:
        if not self._known_dev_classes:
            for controller in self.controllers:
                self._known_dev_classes[controller.ITEM_CLS] = []
                for cls in controller.ITEM_TYPES:
                    self._known_dev_classes[controller.ITEM_CLS].append(cls.value)
        return self._known_dev_classes

    def add_device(self, device_id: str) -> None:
        self._known_devs.add(device_id)

    def remove_device(self, device_id: str) -> None:
        self._known_devs.remove(device_id)

    @property
    def account_id(self) -> str:
        """Get the account ID for the HubSpace account"""
        return self._account_id

    def set_polling_interval(self, polling_interval: int) -> None:
        self._events.polling_interval = polling_interval

    async def close(self) -> None:
        """Close connection and cleanup."""
        await self.events.stop()
        if self._web_session:
            await self._web_session.close()
        self.logger.info("Connection to bridge closed.")

    def subscribe(
        self,
        callback: EventCallBackType,
    ) -> Callable:
        """
        Subscribe to status changes for all resources.

        Returns:
            function to unsubscribe.
        """
        unsubscribes = [
            controller.subscribe(callback) for controller in self.controllers
        ]

        def unsubscribe():
            for unsub in unsubscribes:
                unsub()

        return unsubscribe

    async def get_account_id(self) -> str:
        """Lookup the account ID associated with the login"""
        self.logger.debug("Querying API for account id")
        headers = {"host": "api2.afero.net"}
        res = await self.request(
            "GET", v1_const.HUBSPACE_ACCOUNT_ID_URL, headers=headers
        )
        return (
            (await res.json()).get("accountAccess")[0].get("account").get("accountId")
        )

    async def initialize(self) -> None:
        """Query HubSpace API for all data"""
        self._account_id = await self.get_account_id()
        hs_data = await self.fetch_data()
        await asyncio.gather(
            *[
                controller.initialize(hs_data)
                for controller in self._controllers
                if not controller.initialized
            ]
        )
        await self._events.initialize()

    async def fetch_data(self) -> list[dict[Any, str]]:
        """Query the API"""
        self.logger.debug("Querying API for all data")
        headers = {
            "host": v1_const.HUBSPACE_DATA_HOST,
        }
        params = {"expansions": "state"}
        res = await self.request(
            "get",
            v1_const.HUBSPACE_DATA_URL.format(self.account_id),
            headers=headers,
            params=params,
        )
        return await res.json()

    @asynccontextmanager
    async def create_request(
        self, method: str, url: str, **kwargs
    ) -> Generator[aiohttp.ClientResponse, None, None]:
        """
        Make a request to any path with V2 request method (auth in header).

        Returns a generator with aiohttp ClientResponse.
        """
        if self._web_session is None:
            connector = aiohttp.TCPConnector(
                limit_per_host=3,
            )
            self._web_session = aiohttp.ClientSession(connector=connector)

        token = await self._auth.token(self._web_session)
        headers = get_headers(
            **{
                "authorization": f"Bearer {token}",
            }
        )
        headers.update(kwargs.get("headers", {}))
        kwargs["headers"] = headers
        kwargs["ssl"] = True
        async with self._web_session.request(method, url, **kwargs) as res:
            yield res

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Make request on the api and return response data."""
        retries = 0
        self.logger.info("Making request [%s] to %s with %s", method, url, kwargs)
        while retries < v1_const.MAX_RETRIES:
            retries += 1
            if retries > 1:
                retry_wait = 0.25 * retries
                await asyncio.sleep(retry_wait)
            async with self.create_request(method, url, **kwargs) as resp:
                # 503 means the service is temporarily unavailable, back off a bit.
                # 429 means the bridge is rate limiting/overloaded, we should back off a bit.
                if resp.status in [429, 503]:
                    continue
                # 403 is bad auth
                elif resp.status == 403:
                    raise web_exceptions.HTTPForbidden()
                await resp.read()
                return resp
        raise ExceededMaximumRetries("Exceeded maximum number of retries")


def get_headers(**kwargs):
    headers = copy.copy(v1_const.DEFAULT_HEADERS)
    headers.update(kwargs)
    return headers