"""Config flow for a iAlarm-MK alarm integration."""

from __future__ import annotations

import logging
from logging import Logger
from typing import Any

from . import libpyialarmmk as ipyialarmmk

import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_CODE,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.config_entries import OptionsFlowWithReload

from homeassistant.core import callback


from .const import DOMAIN, ATTR_CODE_DISARM_REQUIRED, ATTR_SENSOR_INSTALL_ENABLED
from .utils import async_get_ialarmmk_mac

_LOGGER: Logger = logging.getLogger(__name__)

# Regex for numbers only (digits 0-9)
NUMBER_ONLY = vol.Match(r"^\d+$")


async def _async_get_device_formatted_mac(
    hass: core.HomeAssistant, username: str, password: str, host: str, port: int
) -> str:
    """Return iAlarm-MK mac address."""

    ialarmmk = ipyialarmmk.iAlarmMkInterface(
        username, password, host, port, logger=_LOGGER
    )
    return await async_get_ialarmmk_mac(hass, ialarmmk)


class iAlarmMkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for iAlarm-MK."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Initial step: credentials and options."""
        errors = {}

        if user_input is not None:
            # Store for next step or final entry
            self._user_data = user_input

            if user_input.get(ATTR_CODE_DISARM_REQUIRED):
                # Go to step to ask for code
                return await self.async_step_code()

            # Otherwise finish immediately
            mac = None
            try:
                mac = await _async_get_device_formatted_mac(
                    self.hass,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    ipyialarmmk.iAlarmMkInterface.IALARMMK_P2P_DEFAULT_HOST,
                    ipyialarmmk.iAlarmMkInterface.IALARMMK_P2P_DEFAULT_PORT,
                )
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            if not errors:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )

        # Show first step form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(ATTR_SENSOR_INSTALL_ENABLED, default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Second step: ask for disarm code if required."""
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_CODE):
                errors["base"] = "missing_code"
            else:
                # Merge code into previous data
                self._user_data.update(user_input)

                # Validate connection / get MAC
                mac = None
                try:
                    mac = await _async_get_device_formatted_mac(
                        self.hass,
                        self._user_data[CONF_USERNAME],
                        self._user_data[CONF_PASSWORD],
                        ipyialarmmk.iAlarmMkInterface.IALARMMK_P2P_DEFAULT_HOST,
                        ipyialarmmk.iAlarmMkInterface.IALARMMK_P2P_DEFAULT_PORT,
                    )
                except ConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

                if not errors:
                    await self.async_set_unique_id(mac)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=self._user_data[CONF_USERNAME], data=self._user_data
                    )

        # Show form to enter code
        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required(CONF_CODE): int}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> iAlarmMkOptionsFlow:
        """Create the options flow."""
        return iAlarmMkOptionsFlow()


USER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SENSOR_INSTALL_ENABLED): bool,
        vol.Required(ATTR_CODE_DISARM_REQUIRED): bool,
    }
)

CODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CODE): int,
    }
)


class iAlarmMkOptionsFlow(OptionsFlowWithReload):
    """Handle options for iAlarm-MK (editable code)."""
    def __init__(self) -> None:
        super().__init__()
        self.options_data: dict[str, Any] = {}

    @property
    def _config(self) -> dict:
        """Return a merged dict of config_entry data + options."""
        merged = dict(self.config_entry.data)
        merged.update(self.config_entry.options or {})
        return merged

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors = {}
        self.options_data.update(self._config)

        if user_input is not None:
            # Save the new options (code)
            self.options_data.update(user_input)

            if user_input.get(ATTR_CODE_DISARM_REQUIRED):
                # Go to step to ask for code
                return await self.async_step_code()


            return self.async_create_entry(data=self.options_data)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, self._config),
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_CODE):
                errors["base"] = "missing_code"
            else:
                self.options_data.update(user_input)

            if not errors:
                self._config.update(user_input)
                return self.async_create_entry(data=self.options_data)

        return self.async_show_form(
            step_id="code",
            data_schema=self.add_suggested_values_to_schema(CODE_SCHEMA, self._config),
        )
