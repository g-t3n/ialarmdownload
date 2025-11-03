"""iAlarm-MK integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from async_timeout import timeout

from . import libpyialarmmk as ipyialarmmk


from homeassistant.components.alarm_control_panel import SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, ATTR_SENSOR_INSTALL_ENABLED
from .utils import async_get_ialarmmk_mac

PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up iAlarm-MK config."""
    host = None  # entry.data[CONF_HOST]
    port = None  # entry.data[CONF_PORT]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    ialarmmk = ipyialarmmk.iAlarmMkInterface(
        username,
        password,
        host,
        port,
        entry.options.get(ATTR_SENSOR_INSTALL_ENABLED, entry.data.get(ATTR_SENSOR_INSTALL_ENABLED, False)),
        hass,
        _LOGGER,
    )

    try:
        async with timeout(10):
            ialarmmk_mac = await async_get_ialarmmk_mac(hass, ialarmmk)
    except (asyncio.TimeoutError, ConnectionError) as ex:
        raise ConfigEntryNotReady from ex

    coordinator = iAlarmMkDataUpdateCoordinator(hass, ialarmmk, ialarmmk_mac)
    coordinator.initialize_sensors()

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload iAlarm-MK config."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: iAlarmMkDataUpdateCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id, None
        )
        if coordinator:
            await coordinator.shutdown()
            coordinator.sensors.clear()  # cleanup custom data
    return unload_ok


def should_pool(self):
    return True


class iAlarmMkDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching iAlarm-MK data."""

    def __init__(
        self, hass: HomeAssistant, ialarmmk: ipyialarmmk.iAlarmMkInterface, mac: str
    ) -> None:
        """Initialize global a iAlarm-MK data updater."""
        self.ialarmmk: ipyialarmmk.iAlarmMkInterface = ialarmmk
        self.state: int = ialarmmk.get_status()
        self.host: str = ialarmmk.host
        self.mac: str = mac
        self.hass = hass
        self.sensors = {}

        self.ialarmmk.set_callback(self.callback)
        self.ialarmmk.set_polling_callback(self.polling_callback)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=5),
        )

        self._subscribe_task = asyncio.create_task(self.ialarmmk.subscribe())
        # self._polling_task = asyncio.create_task(self.ialarmmk.polling())

    def callback(self, status):
        _LOGGER.debug("iAlarm-MK status: %s", status)
        self.state = status
        self.async_set_updated_data(status)

    def polling_callback(self):
        self.async_set_updated_data(self.state)

    def _update_data(self) -> None:
        """Fetch data from iAlarm-MK via sync functions."""
        # status: int = self.ialarmmk.get_status()
        # for sensor_id in self.sensors:
        #    self.sensors[sensor_id]["state"] = self.ialarmmk.get_sensor_status(sensor_id)
        # self.state = status

    def initialize_sensors(self):
        """Query the alarm for sensors and initialize them."""
        self.sensors = (
            self.ialarmmk.get_sensors()
        )  # returns list of dicts with id and zone

    async def _async_update_data(self) -> None:
        """Fetch data from iAlarm-MK."""
        await self.ialarmmk.polling_once()
        # try:
        #    async with timeout(10):
        #        await self.hass.async_add_executor_job(self._update_data)
        # except ConnectionError as error:
        #    raise UpdateFailed(error) from error

    async def shutdown(self):
        """Cleanly stop background tasks when integration unloads."""
        self.ialarmmk.query_sensor = False

        if self._subscribe_task:
            self._subscribe_task.cancel()
            try:
                await self._subscribe_task
            except asyncio.CancelledError:
                pass

        # Optionally tell your library to disconnect
        if hasattr(self.ialarmmk, "disconnect"):
            await self.hass.async_add_executor_job(self.ialarmmk.disconnect)
