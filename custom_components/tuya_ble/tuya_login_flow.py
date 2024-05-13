from typing import Any

from homeassistant.components.tuya.config_flow import TuyaConfigFlow
from homeassistant.data_entry_flow import FlowResult, FlowHandler


class TuyaLoginFlow:
    """Wrapper for Tuya Intergation Config Flow"""

    def __init__(self):
        """Initialize the config flow."""
        self.login_flow = TuyaConfigFlow()

    async def async_step_user(self,
                              user_input: dict[str, Any]) -> FlowResult:
        """Handle a flow initialized by the user"""
        return await self.login_flow.async_step_user(user_input)
