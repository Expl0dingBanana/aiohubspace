"""Controller holding and managing Hubspace resources of type `light`."""

from contextlib import suppress

from ... import device
from ...device import HubspaceDevice, HubspaceState
from ...util import process_range
from ..models import features
from ..models.light import Light, LightPut
from ..models.resource import DeviceInformation, ResourceTypes
from .base import BaseResourcesController


def process_names(values: list[dict]) -> set[str]:
    vals = set()
    for val in values:
        vals.add(val["name"])
    return vals


class LightController(BaseResourcesController[Light]):
    """Controller holding and managing Hubspace resources of type `light`."""

    ITEM_TYPE_ID = ResourceTypes.DEVICE
    ITEM_TYPES = [ResourceTypes.LIGHT]
    ITEM_CLS = Light
    ITEM_MAPPING = {
        "color": "color-rgb",
        "color_mode": "color-mode",
        "color_temperature": "color-temperature",
        "dimming": "brightness",
        "effect": "color-sequence",
    }

    async def turn_on(self, device_id: str) -> None:
        """Turn on the light."""
        await self.set_state(device_id, on=True)

    async def turn_off(self, device_id: str) -> None:
        """Turn off the light."""
        await self.set_state(device_id, on=False)

    async def set_color_temperature(self, device_id: str, temperature: int) -> None:
        """Set Color Temperature to light. Turn on light if it's currently off."""
        await self.set_state(
            device_id, on=True, temperature=temperature, color_mode="white"
        )

    async def set_brightness(self, device_id: str, brightness: int) -> None:
        """Set brightness of the light. Turn on light if it's currently off."""
        await self.set_state(device_id, on=True, brightness=brightness)

    async def set_rgb(self, device_id: str, red: int, green: int, blue: int) -> None:
        """Set RGB of the light. Turn on light if it's currently off."""
        await self.set_state(
            device_id, on=True, color=(red, green, blue), color_mode="color"
        )

    async def set_effect(self, device_id: str, effect: str) -> None:
        """Set effect of the light. Turn on light if it's currently off."""
        await self.set_state(device_id, on=True, effect=effect, color_mode="sequence")

    async def initialize_elem(self, hs_device: HubspaceDevice) -> Light:
        """Initialize the element"""
        self._logger.info("Initializing %s", hs_device.id)
        available: bool = False
        on: features.OnFeature | None = None
        color_temp: features.ColorTemperatureFeature | None = None
        color: features.ColorFeature | None = None
        color_mode: features.ColorModeFeature | None = None
        dimming: features.DimmingFeature | None = None
        effect: features.EffectFeature | None = None
        for state in hs_device.states:
            func_def = device.get_function_from_device(
                hs_device, state.functionClass, state.functionInstance
            )
            if state.functionClass == "power":
                on = features.OnFeature(
                    on=state.value == "on",
                    func_class=state.functionClass,
                    func_instance=state.functionInstance,
                )
            elif state.functionClass == "color-temperature":
                if len(func_def["values"]) > 1:
                    avail_temps = process_color_temps(func_def["values"])
                else:
                    avail_temps = process_range(func_def["values"][0])
                prefix = "K" if func_def.get("type", None) != "numeric" else ""
                current_temp = state.value
                if isinstance(current_temp, str) and current_temp.endswith("K"):
                    current_temp = current_temp[:-1]
                color_temp = features.ColorTemperatureFeature(
                    temperature=int(current_temp), supported=avail_temps, prefix=prefix
                )
            elif state.functionClass == "brightness":
                temp_bright = process_range(func_def["values"][0])
                dimming = features.DimmingFeature(
                    brightness=int(state.value), supported=temp_bright
                )
            elif state.functionClass == "color-sequence":
                current_effect = state.value
                effects = process_effects(hs_device.functions)
                effect = features.EffectFeature(effect=current_effect, effects=effects)
            elif state.functionClass == "color-rgb":
                color = features.ColorFeature(
                    red=state.value["color-rgb"].get("r", 0),
                    green=state.value["color-rgb"].get("g", 0),
                    blue=state.value["color-rgb"].get("b", 0),
                )
            elif state.functionClass == "color-mode":
                color_mode = features.ColorModeFeature(state.value)
            elif state.functionClass == "available":
                available = state.value

        self._items[hs_device.id] = Light(
            hs_device.functions,
            id=hs_device.id,
            available=available,
            device_information=DeviceInformation(
                device_class=hs_device.device_class,
                default_image=hs_device.default_image,
                default_name=hs_device.default_name,
                manufacturer=hs_device.manufacturerName,
                model=hs_device.model,
                name=hs_device.friendly_name,
                parent_id=hs_device.device_id,
            ),
            on=on,
            dimming=dimming,
            color_mode=color_mode,
            color_temperature=color_temp,
            color=color,
            effect=effect,
        )
        return self._items[hs_device.id]

    async def update_elem(self, hs_device: HubspaceDevice) -> set:
        cur_item = self.get_device(hs_device.id)
        updated_keys = set()
        color_seq_states: dict[str, HubspaceState] = {}
        for state in hs_device.states:
            if state.functionClass == "power":
                new_val = state.value == "on"
                if cur_item.on.on != new_val:
                    cur_item.on.on = new_val
                    updated_keys.add("on")
            elif state.functionClass == "color-temperature":
                current_temp = state.value
                if isinstance(current_temp, str) and current_temp.endswith("K"):
                    current_temp = current_temp[:-1]
                new_val = int(current_temp)
                if cur_item.color_temperature.temperature != new_val:
                    cur_item.color_temperature.temperature = new_val
                    updated_keys.add("color_temperature")
            elif state.functionClass == "brightness":
                new_val = int(state.value)
                if cur_item.dimming.brightness != new_val:
                    cur_item.dimming.brightness = int(state.value)
                    updated_keys.add("dimming")
            elif state.functionClass == "color-sequence":
                color_seq_states[state.functionInstance] = state
            elif state.functionClass == "color-rgb":
                color_red = state.value["color-rgb"].get("r", 0)
                color_green = state.value["color-rgb"].get("g", 0)
                color_blue = state.value["color-rgb"].get("b", 0)
                if (
                    cur_item.color.red != color_red
                    or cur_item.color.green != color_green
                    or cur_item.color.blue != color_blue
                ):
                    cur_item.color.red = color_red
                    cur_item.color.green = color_green
                    cur_item.color.blue = color_blue
                    updated_keys.add("color")
            elif state.functionClass == "color-mode":
                if cur_item.color_mode.mode != state.value:
                    cur_item.color_mode.mode = state.value
                    updated_keys.add("color_mode")
            elif state.functionClass == "available":
                if cur_item.available != state.value:
                    cur_item.available = state.value
                    updated_keys.add("available")
        # Several states hold the effect, but its always derived from the preset functionInstance
        if color_seq_states:
            preset_val = (
                color_seq_states["preset"].value
                if "preset" in color_seq_states
                else None
            )
            if preset_val and cur_item.effect.is_preset(preset_val):
                if cur_item.effect.effect != preset_val:
                    cur_item.effect.effect = preset_val
                    updated_keys.add("effect")
            elif preset_val:
                new_val = color_seq_states[color_seq_states["preset"].value].value
                if cur_item.effect.effect != new_val:
                    cur_item.effect.effect = color_seq_states[
                        color_seq_states["preset"].value
                    ].value
                    updated_keys.add("effect")
        return updated_keys

    async def set_state(
        self,
        device_id: str,
        on: bool | None = None,
        temperature: int | None = None,
        brightness: int | None = None,
        color_mode: str | None = None,
        color: tuple[int, int, int] | None = None,
        effect: str | None = None,
    ) -> None:
        """Set supported feature(s) to fan resource."""
        update_obj = LightPut()
        cur_item = self.get_device(device_id)
        if on is not None:
            update_obj.on = features.OnFeature(
                on=on,
                func_class=cur_item.on.func_class,
                func_instance=cur_item.on.func_instance,
            )
        if temperature is not None and cur_item.color_temperature is not None:
            adjusted_temp = min(
                cur_item.color_temperature.supported,
                key=lambda x: abs(x - temperature),
            )
            update_obj.color_temperature = features.ColorTemperatureFeature(
                temperature=adjusted_temp,
                supported=cur_item.color_temperature.supported,
                prefix=cur_item.color_temperature.prefix,
            )
        if brightness is not None and cur_item.dimming is not None:
            update_obj.dimming = features.DimmingFeature(
                brightness=brightness, supported=cur_item.dimming.supported
            )
        if color is not None and cur_item.color is not None:
            update_obj.color = features.ColorFeature(
                red=color[0], green=color[1], blue=color[2]
            )
        if color_mode is not None and cur_item.color_mode is not None:
            update_obj.color_mode = features.ColorModeFeature(mode=color_mode)
        if effect is not None and cur_item.effect is not None:
            update_obj.effect = features.EffectFeature(
                effect=effect, effects=cur_item.effect.effects
            )
        await self.update(device_id, obj_in=update_obj)


def process_color_temps(color_temps: dict) -> list[int]:
    """Determine the supported color temps

    :param color_temps: Result from functions["values"]
    """
    supported_temps = []
    for temp in color_temps:
        color_temp = temp["name"]
        if isinstance(color_temp, str) and color_temp.endswith("K"):
            color_temp = color_temp[0:-1]
        supported_temps.append(int(color_temp))
    return sorted(supported_temps)


def process_effects(functions: list[dict]) -> dict[str, set]:
    """Determine the supported effects"""
    supported_effects = {}
    for function in functions:
        if function["functionClass"] == "color-sequence":
            supported_effects[function["functionInstance"]] = set(
                process_names(function["values"])
            )
    # custom shouldnt be a value in preset
    with suppress(KeyError):
        supported_effects["preset"].remove("custom")
    return supported_effects
