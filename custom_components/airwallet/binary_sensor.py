"""Binary sensors: machine running, my laundry running."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirwalletConfigEntry, AirwalletCoordinator
from .entity import AirwalletLocationEntity, AirwalletMachineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AirwalletConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [MyLaundrySensor(coordinator)]
    entities += [RunningSensor(coordinator, machine_id) for machine_id in coordinator.data.location.machines]
    async_add_entities(entities)


class RunningSensor(AirwalletMachineEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: AirwalletCoordinator, machine_id: str) -> None:
        super().__init__(coordinator, machine_id, "running")

    @property
    def is_on(self) -> bool:
        return self.machine.in_use()


class MyLaundrySensor(AirwalletLocationEntity, BinarySensorEntity):
    """On while at least one of my machines runs."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: AirwalletCoordinator) -> None:
        super().__init__(coordinator, "my_laundry")

    def _my_running(self) -> list[str]:
        machines = self.coordinator.data.location.machines.values()
        return [m.name for m in machines if m.in_use() and self.coordinator.is_mine(m.id)]

    @property
    def is_on(self) -> bool:
        return bool(self._my_running())

    @property
    def extra_state_attributes(self) -> dict:
        return {"machines": self._my_running()}
