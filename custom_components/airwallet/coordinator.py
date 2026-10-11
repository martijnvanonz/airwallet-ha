"""Polling coordinator for Airwallet."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AirwalletAuthError, AirwalletClient, AirwalletError, Location, my_machine_ids
from .const import CONF_LOCATION_ID, CONF_REFRESH_TOKEN, DOMAIN, EVENT_FINISHED, EVENT_STARTED, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type AirwalletConfigEntry = ConfigEntry[AirwalletCoordinator]


@dataclass
class AirwalletData:
    location: Location
    mine: set[str]
    updated: float


class AirwalletCoordinator(DataUpdateCoordinator[AirwalletData]):
    """Fetch the laundry room every minute and fire events on start/finish."""

    config_entry: AirwalletConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AirwalletConfigEntry, client: AirwalletClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = client
        self.location_id: str = entry.data[CONF_LOCATION_ID]
        # Machines that were "mine" when they started. Kept until they finish, so the
        # finish event still knows it was my wash.
        self._my_running: set[str] = set()
        # Device registry id of the laundry room device (set in async_setup_entry).
        self.location_device_id: str | None = None

    async def _async_update_data(self) -> AirwalletData:
        try:
            location = await self.client.get_location(self.location_id)
            orders = await self.client.get_recent_orders()
        except AirwalletAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AirwalletError as err:
            raise UpdateFailed(str(err)) from err
        except TimeoutError as err:
            raise UpdateFailed("timeout") from err

        self._save_refresh_token()
        now = time.time()
        mine = my_machine_ids(location, orders)
        self._fire_events(location, mine, now)
        return AirwalletData(location=location, mine=mine, updated=now)

    def _fire_events(self, location: Location, mine: set[str], now: float) -> None:
        old = self.data.location.machines if self.data else {}
        previous_poll = self.data.updated if self.data else now
        for machine in location.machines.values():
            running = machine.in_use(now)
            if running and machine.id in mine:
                self._my_running.add(machine.id)
            before = old.get(machine.id)
            if before is None:
                continue
            was_running = before.in_use(previous_poll)
            payload = {
                "location_id": location.id,
                "machine_id": machine.id,
                "name": machine.name,
                "product_type": machine.product_type,
                "mine": machine.id in mine or machine.id in self._my_running,
            }
            if running and machine.last_payment > before.last_payment:
                self.hass.bus.async_fire(EVENT_STARTED, payload)
            elif was_running and not running:
                self.hass.bus.async_fire(EVENT_FINISHED, payload)
            if not running:
                self._my_running.discard(machine.id)

    def _save_refresh_token(self) -> None:
        token = self.client.refresh_token
        if token and token != self.config_entry.data.get(CONF_REFRESH_TOKEN):
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, CONF_REFRESH_TOKEN: token}
            )

    def is_mine(self, machine_id: str) -> bool:
        return bool(self.data) and (machine_id in self.data.mine or machine_id in self._my_running)
