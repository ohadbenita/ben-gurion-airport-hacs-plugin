"""Config flow for the Ben Gurion Airport integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_BOARD_LIMIT,
    CONF_INCLUDE_COMPLETED,
    CONF_REFRESH_MINUTES,
    DEFAULT_BOARD_LIMIT,
    DEFAULT_INCLUDE_COMPLETED,
    DEFAULT_REFRESH_MINUTES,
    DOMAIN,
    NAME,
)


def _build_schema(
    user_input: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the options schema."""
    user_input = user_input or {}

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=user_input.get(CONF_NAME, NAME)): str,
            vol.Required(
                CONF_REFRESH_MINUTES,
                default=user_input.get(CONF_REFRESH_MINUTES, DEFAULT_REFRESH_MINUTES),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            vol.Required(
                CONF_BOARD_LIMIT,
                default=user_input.get(CONF_BOARD_LIMIT, DEFAULT_BOARD_LIMIT),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
            vol.Required(
                CONF_INCLUDE_COMPLETED,
                default=user_input.get(CONF_INCLUDE_COMPLETED, DEFAULT_INCLUDE_COMPLETED),
            ): bool,
        }
    )


class BenGurionAirportConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ben Gurion Airport."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_build_schema())

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=user_input[CONF_NAME],
            data=user_input,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return BenGurionAirportOptionsFlow(config_entry)


class BenGurionAirportOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Ben Gurion Airport."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {
            CONF_REFRESH_MINUTES: self.config_entry.options.get(
                CONF_REFRESH_MINUTES, self.config_entry.data[CONF_REFRESH_MINUTES]
            ),
            CONF_BOARD_LIMIT: self.config_entry.options.get(
                CONF_BOARD_LIMIT, self.config_entry.data[CONF_BOARD_LIMIT]
            ),
            CONF_INCLUDE_COMPLETED: self.config_entry.options.get(
                CONF_INCLUDE_COMPLETED, self.config_entry.data[CONF_INCLUDE_COMPLETED]
            ),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REFRESH_MINUTES,
                        default=current[CONF_REFRESH_MINUTES],
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Required(
                        CONF_BOARD_LIMIT,
                        default=current[CONF_BOARD_LIMIT],
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                    vol.Required(
                        CONF_INCLUDE_COMPLETED,
                        default=current[CONF_INCLUDE_COMPLETED],
                    ): bool,
                }
            ),
        )
