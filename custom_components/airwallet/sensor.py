"""Sensors: machine status, busy-until time, free machine counts."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATE_AVAILABLE, STATE_IN_USE, STATE_MAINTENANCE, STATE_MINE
from .coordinator import AirwalletConfigEntry, AirwalletCoordinator
from .entity import AirwalletLocationEntity, AirwalletMachineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AirwalletConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        FreeCountSensor(coordinator, "WASHER", "free_washers"),
        FreeCountSensor(coordinator, "DRYER", "free_dryers"),
    ]
    for machine_id in coordinator.data.location.machines:
        entities += [StatusSensor(coordinator, machine_id), BusyUntilSensor(coordinator, machine_id)]
    async_add_entities(entities)


class StatusSensor(AirwalletMachineEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATE_AVAILABLE, STATE_IN_USE, STATE_MINE, STATE_MAINTENANCE]

    def __init__(self, coordinator: AirwalletCoordinator, machine_id: str) -> None:
        super().__init__(coordinator, machine_id, "status")

    @property
    def native_value(self) -> str:
        machine = self.machine
        if machine.maintenance:
            return STATE_MAINTENANCE
        if not machine.in_use():
            return STATE_AVAILABLE
        return STATE_MINE if self.coordinator.is_mine(machine.id) else STATE_IN_USE

    @property
    def extra_state_attributes(self) -> dict:
        machine = self.machine
        return {
            "product_type": machine.product_type,
            "price_cents": machine.price,
            "last_payment": datetime.fromtimestamp(machine.last_payment, timezone.utc).isoformat(),
        }


class BusyUntilSensor(AirwalletMachineEntity, SensorEntity):
    """When the machine is free again. While a wash runs this is the paid maximum; it moves to the
    real end time when the machine stops."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: AirwalletCoordinator, machine_id: str) -> None:
        super().__init__(coordinator, machine_id, "busy_until")

    @property
    def native_value(self) -> datetime | None:
        machine = self.machine
        return datetime.fromtimestamp(machine.last_used, timezone.utc) if machine.in_use() else None


class FreeCountSensor(AirwalletLocationEntity, SensorEntity):
    _attr_native_unit_of_measurement = "machines"

    def __init__(self, coordinator: AirwalletCoordinator, product_type: str, key: str) -> None:
        super().__init__(coordinator, key)
        self._product_type = product_type

    @property
    def native_value(self) -> int:
        return sum(
            1
            for m in self.coordinator.data.location.machines.values()
            if m.product_type == self._product_type and not m.in_use() and not m.maintenance
        )
