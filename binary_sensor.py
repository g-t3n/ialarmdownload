from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import device_registry
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from . import iAlarmMkDataUpdateCoordinator

from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)
from homeassistant.helpers import entity_registry as er


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    await cleanup_removed_sensors(hass, list(coordinator.sensors.keys()))

    for sensor_id, sensor in coordinator.sensors.items():
        if len(sensor_id) == 0:
            continue
        entities.append(iAlarmMkBinarySensor(coordinator, sensor))

    async_add_entities(entities)


async def cleanup_removed_sensors(hass, current_sensor_ids: list[str]):
    """Remove sensor entities not found anymore on the alarm system."""
    entity_registry = er.async_get(hass)
    ids_to_remove = []

    # Loop through all entities of your domain
    for entity_id, entity_entry in list(entity_registry.entities.items()):
        # Check that it belongs to your integration
        if entity_entry.platform != DOMAIN:
            continue

        # You can also check that it’s a binary_sensor if you only want those
        if entity_entry.domain != "binary_sensor":
            continue

        # Example: your sensor unique_id is the alarm sensor id
        if entity_entry.unique_id not in current_sensor_ids:
            # Remove it from HA
            ids_to_remove.append(entity_entry.entity_id)

    for entity_id in ids_to_remove:
        _LOGGER.info("Removing iAlarm-MK sensor entity: %s", entity_id)
        entity_registry.async_remove(entity_entry.entity_id)


class iAlarmMkBinarySensor(
    CoordinatorEntity[iAlarmMkDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a iAlarm-MK binary sensor."""

    def __init__(self, coordinator: iAlarmMkDataUpdateCoordinator, sensor):
        super().__init__(coordinator)
        self._sensor = sensor
        self._attr_name = f"{sensor['zone']['Name']}"
        self._attr_unique_id = f"{sensor['id']}"
        self._attr_device_class = sensor.get("class", "door")
        self.entity_id = f"binary_sensor.ialarmmk_{sensor['zone']['Name'].lower().replace(' ', '_')}_{sensor['id'].lower().replace(' ', '_')}"
        self._attr_device_info = DeviceInfo(
            manufacturer="iAlarm-MK",
            name=f"Sensori iAlarm-MK",
            connections={(device_registry.CONNECTION_NETWORK_MAC, coordinator.mac)},
        )

    @property
    def _config(self) -> dict:
        """Return a merged dict of config_entry data + options."""
        merged = dict(self.coordinator.config_entry.data)
        merged.update(self.coordinator.config_entry.options or {})
        return merged

    @property
    def is_on(self):
        return self.coordinator.ialarmmk.is_sensor_open(self._sensor["id"])

    @property
    def available(self):
        return self.coordinator.state != "unavailable"

    @property
    def extra_state_attributes(self):
        status = self.coordinator.ialarmmk.get_sensor_status(self._sensor["id"])
        attrs = {}
        if status in (17, 25):
            attrs["battery_warning"] = True
            attrs["battery_level"] = "low"
        else:
            attrs["battery_warning"] = False
            attrs["battery_level"] = "normal"
        return attrs

    @property
    def icon(self):
        status = self.coordinator.ialarmmk.get_sensor_status(self._sensor["id"])
        if status in (17, 25):
            return "mdi:battery-alert"
        elif status in (3, 11, 19, 27):
            return "mdi:bell-alert"
            # 🧠 otherwise, return the default icon for its device_class
        return super().icon

    async def async_will_remove_from_hass(self):
        # Remove from internal structures
        del self.coordinator.sensors[self._sensor["id"]]
