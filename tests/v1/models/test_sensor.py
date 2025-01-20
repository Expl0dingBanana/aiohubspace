from aiohubspace.v1.models.sensor import HubspaceSensor, HubspaceSensorError


def test_init_sensor():
    dev = HubspaceSensor(
        id="entity-1",
        owner="device-link",
        _value="cool",
        unit="beans",
    )
    assert dev.value == "cool"
    assert dev.unit == "beans"


def test_init_sensor_error():
    dev = HubspaceSensorError(
        id="entity-1",
        owner="device-link",
        _value="alerting",
        unit="beans",
    )
    assert dev.value is True
    dev.value = "normal"
    assert dev.value is False
