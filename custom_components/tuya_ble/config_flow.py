"""Config flow for Tuya BLE integration."""

from __future__ import annotations

import logging
import pycountry
from typing import Any

import voluptuous as vol
from tuya_sharing import LoginControl


from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowHandler, FlowResult

from homeassistant.components.tuya.const import (
    CONF_ENDPOINT,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_USER_CODE,
    DOMAIN,
    TUYA_CLIENT_ID,
    TUYA_RESPONSE_CODE,
    TUYA_RESPONSE_MSG,
    TUYA_RESPONSE_QR_CODE,
    TUYA_RESPONSE_RESULT,
    TUYA_RESPONSE_SUCCESS,
    TUYA_SCHEMA,
)

from .tuya_ble import SERVICE_UUID, TuyaBLEDeviceCredentials

from .const import (
    DOMAIN,
    CONF_AUTH_TYPE,
    SMARTLIFE_APP,
    TUYA_SMART_APP,
)
from .devices import TuyaBLEData, get_device_readable_name
from .cloud import HASSTuyaBLEDeviceManager
from .tuya_login_flow import TuyaLoginFlow

_LOGGER = logging.getLogger(__name__)
_tuya_login = TuyaLoginFlow()


async def async_step_login(
        user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Handle the Tuya IOT platform login step."""
    return await _tuya_login.async_step_user(user_input)


class TuyaBLEOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle a Tuya BLE options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_step_login(user_input)

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the Tuya IOT platform login step."""
        errors: dict[str, str] = {}
        placeholders: dict[str, Any] = {}
        credentials: TuyaBLEDeviceCredentials | None = None
        address: str | None = self.config_entry.data.get(CONF_ADDRESS)

        if user_input is not None:
            entry: TuyaBLEData | None = None
            domain_data = self.hass.data.get(DOMAIN)
            if domain_data:
                entry = domain_data.get(self.config_entry.entry_id)
            if entry:
                login_data = await async_step_login(user_input)
                if login_data:
                    credentials = await entry.manager.get_device_credentials(
                        address, True, True
                    )
                    if credentials:
                        return self.async_create_entry(
                            title=self.config_entry.title,
                            data=entry.manager.data,
                        )
                    else:
                        errors["base"] = "device_not_registered"

        if user_input is None:
            user_input = {}
            user_input.update(self.config_entry.options)

        return await async_step_login(user_input)


class TuyaBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tuya BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._data: dict[str, Any] = {}
        self._manager: HASSTuyaBLEDeviceManager | None = None
        self._get_device_info_error = False

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)
        await self._manager.build_cache()
        self.context["title_placeholders"] = {
            "name": await get_device_readable_name(
                discovery_info,
                self._manager,
            )
        }
        return await async_step_login()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step."""
        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)
        await self._manager.build_cache()
        return await async_step_login()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            local_name = await get_device_readable_name(discovery_info, self._manager)
            await self.async_set_unique_id(
                discovery_info.address, raise_on_progress=False
            )
            self._abort_if_unique_id_configured()
            credentials = await self._manager.get_device_credentials(
                discovery_info.address, self._get_device_info_error, True
            )
            self._data[CONF_ADDRESS] = discovery_info.address
            if credentials is None:
                self._get_device_info_error = True
                errors["base"] = "device_not_registered"
            else:
                return self.async_create_entry(
                    title=local_name,
                    data={CONF_ADDRESS: discovery_info.address},
                    options=self._data,
                )

        if discovery := self._discovery_info:
            self._discovered_devices[discovery.address] = discovery
        else:
            current_addresses = self._async_current_ids()
            for discovery in async_discovered_service_info(self.hass):
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                    or discovery.service_data is None
                    or not SERVICE_UUID in discovery.service_data.keys()
                ):
                    continue
                self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return self.async_abort(reason="no_unconfigured_devices")

        def_address: str
        if user_input:
            def_address = user_input.get(CONF_ADDRESS)
        else:
            def_address = list(self._discovered_devices)[0]

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ADDRESS,
                        default=def_address,
                    ): vol.In(
                        {
                            service_info.address: await get_device_readable_name(
                                service_info,
                                self._manager,
                            )
                            for service_info in self._discovered_devices.values()
                        }
                    ),
                },
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TuyaBLEOptionsFlow:
        """Get the options flow for this handler."""
        return TuyaBLEOptionsFlow(config_entry)
