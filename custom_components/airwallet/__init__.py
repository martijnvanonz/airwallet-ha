"""Airwallet laundry integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AirwalletClient
from .const import CONF_PHONE, CONF_PIN, CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import AirwalletConfigEntry, AirwalletCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AirwalletConfigEntry) -> bool:
    client = AirwalletClient(
        async_get_clientsession(hass),
        entry.data[CONF_PHONE],
        entry.data[CONF_PIN],
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
    )
    coordinator = AirwalletCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    # Register the laundry room first, so machines can link to it with via_device_id.
    location = coordinator.data.location
    coordinator.location_device_id = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, location.id)},
        name=location.name,
        manufacturer="Airwallet",
        model="Laundry room",
    ).id
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AirwalletConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
