"""End-to-end tests with a fake Airwallet client."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.airwallet.api import PUSH_CHARS, AirwalletAuthError, Location, Machine
from custom_components.airwallet.const import DOMAIN, EVENT_FINISHED, SCAN_INTERVAL

LOC = "-NxExampleLocation01"


def push_id(ts: float) -> str:
    ms = int(ts * 1000)
    chars = []
    for _ in range(8):
        chars.append(PUSH_CHARS[ms % 64])
        ms //= 64
    return "".join(reversed(chars)) + "abcdefghijkl"


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        now = time.time()
        self.refresh_token = "rt"
        self.uid = "uid"
        self.machines = {
            "w3": dict(name="Wasmachine 3", product_type="WASHER", last_payment_timestamp=now - 600, last_used=now + 9000),
            "w5": dict(name="Wasmachine 5", product_type="WASHER", last_payment_timestamp=now - 600, last_used=now + 9000),
            "w6": dict(name="Wasmachine 6", product_type="WASHER", last_payment_timestamp=now - 9000, last_used=now - 6000),
            "d1": dict(name="Droger 1", product_type="DRYER", last_payment_timestamp=now - 9000, last_used=now - 6000),
        }
        # I paid for w3; someone else for w5.
        self.orders = {push_id(now - 600): {"device_id": "w3"}}

    async def login(self) -> None:
        pass

    async def get_favorite_location_id(self) -> str:
        return LOC

    async def get_location(self, location_id: str) -> Location:
        machines = {k: Machine.from_dict({"id": k, **v}) for k, v in self.machines.items()}
        return Location(id=location_id, name="Example Laundry", machines=machines)

    async def get_recent_orders(self, limit: int = 10):
        return self.orders


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def fake():
    client = FakeClient()
    with (
        patch("custom_components.airwallet.AirwalletClient", return_value=client),
        patch("custom_components.airwallet.config_flow.AirwalletClient", return_value=client),
    ):
        yield client


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=LOC, data={"phone": "+31600000000", "pin": "123456", "location_id": LOC})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities(hass: HomeAssistant, fake: FakeClient) -> None:
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.wasmachine_3_status").state == "mine"
    assert hass.states.get("sensor.wasmachine_5_status").state == "in_use"
    assert hass.states.get("sensor.wasmachine_6_status").state == "available"
    assert hass.states.get("binary_sensor.wasmachine_3_running").state == "on"
    assert hass.states.get("sensor.wasmachine_6_busy_until").state == "unknown"
    assert hass.states.get("sensor.example_laundry_free_washers").state == "1"
    assert hass.states.get("sensor.example_laundry_free_dryers").state == "1"
    my = hass.states.get("binary_sensor.example_laundry_my_laundry_running")
    assert my.state == "on" and my.attributes["machines"] == ["Wasmachine 3"]


async def test_finished_events(hass: HomeAssistant, fake: FakeClient) -> None:
    await setup(hass)
    events = []
    hass.bus.async_listen(EVENT_FINISHED, lambda e: events.append(e.data))

    # The boxes report the real end time: both washes stopped a moment ago.
    fake.machines["w3"]["last_used"] = time.time() - 5
    fake.machines["w5"]["last_used"] = time.time() - 5
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    by_name = {e["name"]: e for e in events}
    assert set(by_name) == {"Wasmachine 3", "Wasmachine 5"}
    assert by_name["Wasmachine 3"]["mine"] is True
    assert by_name["Wasmachine 5"]["mine"] is False
    assert hass.states.get("sensor.wasmachine_3_status").state == "available"
    assert hass.states.get("sensor.example_laundry_free_washers").state == "3"
    assert hass.states.get("binary_sensor.example_laundry_my_laundry_running").state == "off"


async def test_auth_failure_starts_reauth(hass: HomeAssistant, fake: FakeClient) -> None:
    async def fail(*args):
        raise AirwalletAuthError("bad")

    fake.get_location = fail
    entry = await setup_failing(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def setup_failing(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=LOC, data={"phone": "+31600000000", "pin": "123456", "location_id": LOC})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, fake: FakeClient) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": "+31600000000", "pin": "123456"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Example Laundry"
    assert result["data"]["location_id"] == LOC


def test_pin_to_password() -> None:
    from custom_components.airwallet.api import phone_to_email, pin_to_password

    assert pin_to_password("1234") == "001234"
    assert pin_to_password(" 0042 ") == "000042"
    assert pin_to_password("001234") == "001234"
    assert phone_to_email("06 12345678") == "+31612345678@airwallet.net"
    assert phone_to_email("+31 6 1234 5678") == "+31612345678@airwallet.net"


async def test_machines_linked_to_room_without_deprecation(hass: HomeAssistant, fake: FakeClient, caplog) -> None:
    from homeassistant.helpers import device_registry as dr

    entry = await setup(hass)
    reg = dr.async_get(hass)
    room = reg.async_get_device_by_identifier((DOMAIN, LOC), entry.entry_id)
    machine = reg.async_get_device_by_identifier((DOMAIN, "w3"), entry.entry_id)
    assert room and machine and machine.via_device_id == room.id
    assert "deprecated `via_device`" not in caplog.text
