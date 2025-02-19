import datetime

import pytest
import pytest_asyncio
from aioresponses import aioresponses

from aiohubspace.v1 import HubspaceBridgeV1
from aiohubspace.v1.auth import token_data
from aiohubspace.v1.controllers.event import EventType


@pytest.fixture
def mocked_bridge(mocker):
    hs_bridge: HubspaceBridgeV1 = HubspaceBridgeV1("username2", "password2")
    mocker.patch.object(
        hs_bridge,
        "get_account_id",
        side_effect=mocker.AsyncMock(return_value="mocked-account-id"),
    )
    mocker.patch.object(hs_bridge, "_account_id", "mocked-account-id")
    mocker.patch.object(hs_bridge, "fetch_data", return_value=[])
    mocker.patch.object(hs_bridge, "request", side_effect=mocker.AsyncMock())
    mocker.patch.object(hs_bridge, "initialize", side_effect=mocker.AsyncMock())
    # Force initialization so test elements are not overwritten
    for controller in hs_bridge._controllers:
        controller._initialized = True

    # Enable ad-hoc event updates
    def emit_event(event_type, data):
        hs_bridge.events.emit(EventType(event_type), data)

    hs_bridge.emit_event = emit_event
    hs_bridge.__aenter__ = mocker.AsyncMock(return_value=hs_bridge)
    hs_bridge.__aexit__ = mocker.AsyncMock()
    yield hs_bridge


@pytest.fixture
def mocked_bridge_req(mocker):
    hs_bridge: HubspaceBridgeV1 = HubspaceBridgeV1("username2", "password2")
    mocker.patch.object(
        hs_bridge,
        "get_account_id",
        side_effect=mocker.AsyncMock(return_value="mocked-account-id"),
    )
    mocker.patch.object(hs_bridge, "_account_id", "mocked-account-id")
    mocker.patch.object(hs_bridge, "initialize", side_effect=mocker.AsyncMock())
    mocker.patch.object(hs_bridge, "fetch_data", side_effect=hs_bridge.fetch_data)
    mocker.patch.object(hs_bridge, "request", side_effect=hs_bridge.request)
    hs_bridge._auth._token_data = token_data(
        "mock-token", expiration=datetime.datetime.now().timestamp() + 200
    )
    hs_bridge._auth._refresh_token = "mock-refresh-token"
    # Force initialization so test elements are not overwritten
    for controller in hs_bridge._controllers:
        controller._initialized = True

    # Enable ad-hoc event updates
    def emit_event(event_type, data):
        hs_bridge.events.emit(EventType(event_type), data)

    hs_bridge.emit_event = emit_event
    hs_bridge.__aenter__ = mocker.AsyncMock(return_value=hs_bridge)
    hs_bridge.__aexit__ = mocker.AsyncMock()
    yield hs_bridge


@pytest_asyncio.fixture
async def bridge(mocker):
    bridge = HubspaceBridgeV1("user", "passwd")
    mocker.patch.object(bridge, "_account_id", "mocked-account-id")
    mocker.patch.object(bridge, "fetch_data", return_value=[])
    mocker.patch.object(bridge, "request", side_effect=mocker.AsyncMock())
    await bridge.initialize()
    yield bridge
    await bridge.close()


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m
