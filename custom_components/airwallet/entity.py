"""Base entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Machine
from .const import DOMAIN
from .coordinator import AirwalletCoordinator


class AirwalletLocationEntity(CoordinatorEntity[AirwalletCoordinator]):
    """Entity that belongs to the laundry room."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirwalletCoordinator, key: str) -> None:
        super().__init__(coordinator)
        location = coordinator.data.location
        self._attr_unique_id = f"{location.id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location.id)},
            name=location.name,
            manufacturer="Airwallet",
            model="Laundry room",
        )


class AirwalletMachineEntity(CoordinatorEntity[AirwalletCoordinator]):
    """Entity that belongs to one machine."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirwalletCoordinator, machine_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.machine_id = machine_id
        machine = self.machine
        self._attr_unique_id = f"{machine_id}_{key}"
        self._attr_translation_key = key
        specs = machine.raw.get("machine_specifications") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, machine_id)},
            name=machine.name,
            manufacturer=specs.get("brand") or "Airwallet",
            model=specs.get("model") or machine.product_type.title(),
            sw_version=machine.raw.get("firmware_version"),
            via_device_id=coordinator.location_device_id,
        )

    @property
    def machine(self) -> Machine:
        return self.coordinator.data.location.machines[self.machine_id]

    @property
    def available(self) -> bool:
        return super().available and self.machine_id in self.coordinator.data.location.machines
