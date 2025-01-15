import asyncio
from unittest.mock import AsyncMock

import pytest

from aiohubspace.v1.controllers import event
from aiohubspace.v1.models.resource import ResourceTypes

from .. import utils

a21_light = utils.create_devices_from_data("light-a21.json")[0]
switch = utils.create_devices_from_data("switch-HPDA311CWB.json")[0]


@pytest.mark.asyncio
async def test_properties(bridge):
    stream = bridge.events
    assert len(stream._bg_tasks) == 2
    stream._status = event.EventStreamStatus.CONNECTING
    assert stream.connected is False
    assert stream.status == event.EventStreamStatus.CONNECTING
    stream._status = event.EventStreamStatus.CONNECTED
    assert stream.connected is True
    stream.polling_interval = 1
    assert stream._polling_interval == 1
    assert stream.polling_interval == 1


@pytest.mark.asyncio
async def test_initialize(bridge):
    stream = bridge.events
    assert len(stream._bg_tasks) == 2


@pytest.mark.asyncio
async def test_stop(bridge):
    stream = bridge.events
    await stream.stop()
    assert len(stream._bg_tasks) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call,event_filter,resource_filter,expected",
    [
        (min, None, None, (min, None, None)),
        (
            min,
            event.EventType.RESOURCE_UPDATED,
            max,
            (min, (event.EventType.RESOURCE_UPDATED,), (max,)),
        ),
        (
            min,
            (event.EventType.RESOURCE_UPDATED, event.EventType.RESOURCE_DELETED),
            max,
            (
                min,
                (event.EventType.RESOURCE_UPDATED, event.EventType.RESOURCE_DELETED),
                (max,),
            ),
        ),
    ],
)
async def test_subscribe(call, event_filter, resource_filter, expected, mocked_bridge):
    events = mocked_bridge.events
    unsub = events.subscribe(call, event_filter, resource_filter)
    assert callable(unsub)
    assert len(events._subscribers) == 1
    assert events._subscribers[0] == expected
    unsub()
    assert len(events._subscribers) == 0


@pytest.mark.asyncio
async def test_event_reader_dev_add(bridge, mocker):
    stream = bridge.events
    stream._subscribers = []
    await stream.stop()

    def hs_dev(dev):
        return dev

    mocker.patch.object(bridge, "fetch_data", AsyncMock(return_value=[a21_light]))
    mocker.patch.object(event, "get_hs_device", side_effect=hs_dev)
    await stream.initialize_reader()
    max_retry = 10
    retry = 0
    while True:
        if retry >= max_retry:
            raise AssertionError("Item never added")
        if stream._event_queue.qsize() == 0:
            retry += 1
            await asyncio.sleep(0.1)
        else:
            break
    assert stream._event_queue.qsize() != 0
    event_to_process = await stream._event_queue.get()
    assert event_to_process == {
        "type": event.EventType.RESOURCE_ADDED,
        "device_id": a21_light.id,
        "device": a21_light,
    }


@pytest.mark.asyncio
async def test_add_job(bridge, mocker):
    stream = bridge.events
    await stream.stop()
    stream.add_job(None)
    assert stream._event_queue.qsize() == 1


@pytest.mark.asyncio
async def test_event_reader_dev_update(bridge, mocker):
    stream = bridge.events
    bridge.lights.initialize({})
    await bridge.lights.initialize_elem(a21_light)
    bridge.add_device(a21_light.id, bridge.lights)
    await stream.stop()

    def hs_dev(dev):
        return dev

    mocker.patch.object(bridge, "fetch_data", AsyncMock(return_value=[a21_light]))
    mocker.patch.object(event, "get_hs_device", side_effect=hs_dev)
    await stream.initialize_reader()
    max_retry = 10
    retry = 0
    while True:
        if retry >= max_retry:
            raise AssertionError("Item never added")
        if stream._event_queue.qsize() == 0:
            retry += 1
            await asyncio.sleep(0.1)
        else:
            break
    assert stream._event_queue.qsize() != 0
    event_to_process = await stream._event_queue.get()
    assert event_to_process == {
        "type": event.EventType.RESOURCE_UPDATED,
        "device_id": a21_light.id,
        "device": a21_light,
    }


@pytest.mark.asyncio
async def test_event_reader_dev_delete(bridge, mocker):
    stream = bridge.events
    bridge.lights.initialize({})
    bridge.lights.initialize_elem(a21_light)
    bridge.add_device(a21_light.id, bridge.lights)
    await stream.stop()

    def hs_dev(dev):
        return dev

    mocker.patch.object(bridge, "fetch_data", AsyncMock(return_value=[]))
    mocker.patch.object(event, "get_hs_device", side_effect=hs_dev)
    await stream.initialize_reader()
    max_retry = 10
    retry = 0
    while True:
        if retry >= max_retry:
            raise AssertionError("Item never added")
        if stream._event_queue.qsize() == 0:
            retry += 1
            await asyncio.sleep(0.1)
        else:
            break
    assert stream._event_queue.qsize() != 0
    event_to_process = await stream._event_queue.get()
    assert event_to_process == {
        "type": event.EventType.RESOURCE_DELETED,
        "device_id": a21_light.id,
    }


@pytest.mark.asyncio
async def test___event_processor(bridge, mocker):
    stream = bridge.events
    emit = mocker.patch.object(stream, "emit")
    exp_event = event.HubspaceEvent(
        type=event.EventType.RESOURCE_DELETED, device_id="1234"
    )
    stream._event_queue.put_nowait(exp_event)
    await stream.initialize_processor()
    max_retry = 10
    retry = 0
    while True:
        if retry >= max_retry:
            raise AssertionError("Item never removed")
        if stream._event_queue.qsize() == 1:
            retry += 1
            await asyncio.sleep(0.1)
        else:
            break
    assert stream._event_queue.qsize() == 0
    emit.assert_called_once_with(exp_event["type"], exp_event)


@pytest.mark.asyncio
@pytest.mark.parametrize("is_coroutine", [True, False])
@pytest.mark.parametrize(
    "event_type, event_filter, expected",
    [
        (event.EventType.RESOURCE_ADDED, (event.EventType.RESOURCE_ADDED,), True),
        (event.EventType.RESOURCE_UPDATED, (event.EventType.RESOURCE_ADDED,), False),
    ],
)
async def test_emit_event_type(
    event_type, event_filter, expected, is_coroutine, bridge, mocker
):
    stream = bridge.events
    stream._subscribers = []
    await stream.stop()

    event_to_emit = event.HubspaceEvent(
        type=event_type, device_id=a21_light.id, device=a21_light
    )

    callback = mocker.AsyncMock() if is_coroutine else mocker.Mock()
    stream.subscribe(callback, event_filter=event_filter)
    stream.emit(event_type, event_to_emit)
    if expected:
        callback.assert_called_once()
    else:
        callback.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_coroutine", [True, False])
@pytest.mark.parametrize(
    "device, resource_filter, expected",
    [
        (a21_light, (ResourceTypes.LIGHT,), True),
        (a21_light, (ResourceTypes.FAN,), False),
        (
            switch,
            (
                ResourceTypes.LIGHT,
                ResourceTypes.FAN,
            ),
            True,
        ),
    ],
)
async def test_emit_resource_filter(
    device, resource_filter, expected, is_coroutine, bridge, mocker
):
    stream = bridge.events
    await stream.stop()

    event_to_emit = event.HubspaceEvent(
        type=event.EventType.RESOURCE_UPDATED, device_id=device.id, device=device
    )

    callback = mocker.AsyncMock() if is_coroutine else mocker.Mock()
    res_filter = tuple(x.value for x in resource_filter)
    stream.subscribe(callback, resource_filter=res_filter)
    stream.emit(event.EventType.RESOURCE_UPDATED, event_to_emit)
    if expected:
        callback.assert_called_once()
    else:
        callback.assert_not_called()


@pytest.mark.asyncio
async def test_emit_resource_filter_exception(bridge, caplog):
    stream = bridge.events
    event_to_emit = event.HubspaceEvent(
        type=event.EventType.RESOURCE_UPDATED,
        device_id="cool_id",
        device="im not a hubspace device",
    )
    stream.subscribe(min, resource_filter=(ResourceTypes.LIGHT.value,))
    stream.emit(event.EventType.RESOURCE_UPDATED, event_to_emit)
    assert "Unhandled exception. Please open a bug report" in caplog.text
