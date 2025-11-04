"""Interfaces with iAlarmMk control panels."""

from __future__ import annotations

import logging
from . import libpyialarmmk as ipyialarmmk

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)


from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CODE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import iAlarmMkDataUpdateCoordinator
from .const import DOMAIN, ATTR_CODE_DISARM_REQUIRED

_LOGGER = logging.getLogger(__name__)


IALARMMK_TO_HASS = {
    ipyialarmmk.iAlarmMkInterface.ARMED_AWAY: AlarmControlPanelState.ARMED_AWAY,
    ipyialarmmk.iAlarmMkInterface.ARMED_STAY: AlarmControlPanelState.ARMED_HOME,
    ipyialarmmk.iAlarmMkInterface.DISARMED: AlarmControlPanelState.DISARMED,
    ipyialarmmk.iAlarmMkInterface.TRIGGERED: AlarmControlPanelState.TRIGGERED,
    ipyialarmmk.iAlarmMkInterface.ALARM_ARMING: AlarmControlPanelState.ARMING,
    ipyialarmmk.iAlarmMkInterface.UNAVAILABLE: AlarmControlPanelState.PENDING,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up a iAlarm-MK alarm control panel based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([iAlarmMkPanel(coordinator)])


class iAlarmMkPanel(
    CoordinatorEntity[iAlarmMkDataUpdateCoordinator], AlarmControlPanelEntity
):
    """Representation of an iAlarm-MK device."""

    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
    )
    _attr_name = "iAlarm-MK"
    _attr_icon = "mdi:security"

    def __init__(self, coordinator: iAlarmMkDataUpdateCoordinator) -> None:
        """Initialize the alarm panel."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.mac
        self._attr_code_arm_required = False
        self._attr_code_format = None
        self._attr_code = self._config.get(CONF_CODE)
        self._attr_device_info = DeviceInfo(
            manufacturer="iAlarm-MK",
            name=self.name,
            connections={(device_registry.CONNECTION_NETWORK_MAC, coordinator.mac)},
        )
        self.logger = _LOGGER

#    @property
#    def state(self) -> AlarmControlPanelState | None:
#        """Return the state of the device."""
#        return IALARMMK_TO_HASS.get(self.coordinator.state)

    @property
    def _config(self) -> dict:
        """Return a merged dict of config_entry data + options."""
        merged = dict(self.coordinator.config_entry.data)
        merged.update(self.coordinator.config_entry.options or {})
        return merged

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        return IALARMMK_TO_HASS.get(self.coordinator.state)

    def alarm_disarm(self, code: str | None = None) -> None:
        # call your coordinator to disarm
        try:
            self.logger.debug("iAlarm-MK Disarming alarm panel")
            if self.code_arm_required and (not code or self._get_code(code) != self._get_code(self._attr_code)):
                self.logger.debug("iAlarm-MK Unable to disarm, wrong code?")
                return

            self.coordinator.ialarmmk.disarm()
        except:
            self.logger.debug("iAlarm-MK Unable to disarm", exc_info=True)

    def alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        self.logger.debug("iAlarm-MK Arming home alarm panel")
        try:
            if self.code_arm_required and (not code or self._get_code(code) != self._get_code(self._attr_code)):
                self.logger.debug("iAlarm-MK Unable to arm home, wrong code?")
                return

            self.coordinator.ialarmmk.arm_stay()
        except:
            self.logger.debug("iAlarm-MK Unable to arm home", exc_info=True)

    def alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        self.logger.debug("iAlarm-MK Arming away alarm panel")
        try:
            if self.code_arm_required and (not code or self._get_code(code) != self._get_code(self._attr_code)):
                self.logger.debug("iAlarm-MK Unable to arm away, wrong code?")
                return

            self.coordinator.ialarmmk.arm_away()
        except:
            self.logger.debug("iAlarm-MK Unable to arm away", exc_info=True)

    @property
    def code_arm_required(self):
        """Whether the code is required for arm actions."""
        # if not self._config or ATTR_CODE_ARM_REQUIRED not in self._config:
        #    return True  # assume code is needed (conservative approach)
        try:
            if (IALARMMK_TO_HASS.get(self.coordinator.state)!= AlarmControlPanelState.DISARMED):
                return self._config.get(ATTR_CODE_DISARM_REQUIRED, False)
        except:
            self.logger.debug("iAlarm-MK Unable to get code_arm_required", exc_info=True)

        return self._attr_code_arm_required

    @property
    def code_format(self):
        """Return whether code consists of digits or characters."""
        try:
            if (
                IALARMMK_TO_HASS.get(self.coordinator.state)
                == AlarmControlPanelState.DISARMED
                and self.code_arm_required
            ):
                return CodeFormat.NUMBER

            if (
                IALARMMK_TO_HASS.get(self.coordinator.state)
                != AlarmControlPanelState.DISARMED
                and self._config
                and self._config.get(ATTR_CODE_DISARM_REQUIRED, False)
            ):
                return CodeFormat.NUMBER
        except:
            self.logger.debug("iAlarm-MK Unable to get code_format", exc_info=True)

        return None

    def _get_code(self,code: str | None = None) -> int:
        """Return code if set."""
        try:
            return int(code)
        except:
            return 0
