"""One switch per map room: ON cleans that room, OFF stops and docks.

Voice assistants handle plain on/off switches in every language, unlike
vacuum zones (Google sends a bare StartStop for "vacuum the kitchen" in
Polish). Several rooms switched on within BATCH_WINDOW seconds ("turn on
kitchen and living-room cleaning" arrives as separate commands) are merged
into one room clean, as is a room added while a room clean is running.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .clean_log import parse_targets
from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import JonrVacuumCoordinator

_LOGGER = logging.getLogger(__name__)

BATCH_WINDOW = 3.0        # s to collect "and ..." rooms into one task
OPTIMISTIC_FOR = 120.0    # s a switched-on room reads ON before the robot reports it
ROOM_TASKS = {8, 9, 10}   # 17.9: room clean running / paused / resumed


def floor_rooms(entry) -> dict[int, tuple[str, dict[int, str]]]:
    coord = entry.runtime_data.map
    if getattr(coord, "is_saved_map", False):
        return coord.floor_rooms
    return {}


class RoomCleanBatcher:
    """Per entry: collects switched-on rooms and fires one clean_segment."""

    def __init__(self, hass: HomeAssistant, entry, control: JonrVacuumCoordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.control = control
        self.pending: dict[int, list[int]] = {}       # map id -> room ids
        self.optimistic: dict[tuple[int, int], float] = {}
        self._unsub: CALLBACK_TYPE | None = None

    def _vacuum_entity_id(self) -> str | None:
        base = self.entry.unique_id or self.entry.entry_id
        return er.async_get(self.hass).async_get_entity_id("vacuum", DOMAIN, f"{base}_vacuum")

    def running_rooms(self) -> set[int]:
        d = self.control.data
        if d is None or d.robot_status_raw not in ROOM_TASKS:
            return set()
        out = set()
        for r in parse_targets(d.clean_values_raw):
            try:
                out.add(int(r))
            except (TypeError, ValueError):
                pass
        return out

    def is_on(self, map_id: int, room_id: int) -> bool:
        coord = self.entry.runtime_data.map
        if room_id in self.pending.get(map_id, []):
            return True
        until = self.optimistic.get((map_id, room_id))
        if until and until > time.monotonic():
            return True
        return map_id == getattr(coord, "active_map_id", None) and room_id in self.running_rooms()

    @callback
    def add(self, map_id: int, room_id: int) -> None:
        active = getattr(self.entry.runtime_data.map, "active_map_id", None)
        if map_id != active:
            floors = floor_rooms(self.entry)
            raise HomeAssistantError(
                f"This room is on floor {floors.get(map_id, ('?',))[0]}, the robot is on "
                f"{floors.get(active, ('?',))[0]}. Carry the robot there and switch the "
                "Active map first.")
        rooms = self.pending.setdefault(map_id, [])
        if room_id not in rooms:
            rooms.append(room_id)
        self.optimistic[(map_id, room_id)] = time.monotonic() + OPTIMISTIC_FOR
        if self._unsub:
            self._unsub()
        self._unsub = async_call_later(self.hass, BATCH_WINDOW, self._fire)

    @callback
    def _fire(self, _now) -> None:
        self._unsub = None
        batch, self.pending = self.pending, {}
        active = getattr(self.entry.runtime_data.map, "active_map_id", None)
        rooms = batch.get(active, [])
        if not rooms:
            return
        # A room added while a room clean runs joins it instead of replacing it.
        running = [r for r in sorted(self.running_rooms()) if r not in rooms]
        self.hass.async_create_task(self._async_clean(running + rooms))

    async def _async_clean(self, rooms: list[int]) -> None:
        eid = self._vacuum_entity_id()
        if eid is None:
            return
        try:
            await self.hass.services.async_call(
                DOMAIN, "clean_segment", {"entity_id": eid, "segments": rooms}, blocking=True)
            _LOGGER.info("Room switches: cleaning rooms %s", rooms)
        except HomeAssistantError as err:
            _LOGGER.error("Room switches: cleaning rooms %s failed: %s", rooms, err)
            for key in list(self.optimistic):
                if key[1] in rooms:
                    self.optimistic.pop(key, None)
            self.control.async_update_listeners()

    async def async_stop(self, map_id: int, room_id: int) -> None:
        self.optimistic.pop((map_id, room_id), None)
        if room_id in self.pending.get(map_id, []):
            self.pending[map_id].remove(room_id)
            return
        if room_id not in self.running_rooms():
            return
        eid = self._vacuum_entity_id()
        if eid:
            await self.hass.services.async_call(
                "vacuum", "return_to_base", {"entity_id": eid}, blocking=True)

    def unload(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None


class RoomCleanSwitch(CoordinatorEntity["JonrVacuumCoordinator"], SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "room_clean"
    _attr_icon = "mdi:robot-vacuum"

    def __init__(self, coordinator, entry, batcher: RoomCleanBatcher, map_id: int,
                 floor: str, multi: bool, room_id: int, room: str) -> None:
        super().__init__(coordinator)
        self._batcher = batcher
        self._map_id = map_id
        self._room_id = room_id
        base = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{base}_room_clean_{map_id}_{room_id}"
        self._attr_translation_placeholders = {
            "room": f"{room} ({floor})" if multi and floor else room}
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, base)})
        self._attr_extra_state_attributes = {"map_id": map_id, "room_id": room_id}

    @property
    def is_on(self) -> bool:
        return self._batcher.is_on(self._map_id, self._room_id)

    async def async_turn_on(self, **kwargs) -> None:
        self._batcher.add(self._map_id, self._room_id)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._batcher.async_stop(self._map_id, self._room_id)
        self.async_write_ha_state()


def _rooms_sig(floors) -> tuple:
    return tuple((mid, tuple(sorted(rooms))) for mid, (_f, rooms) in sorted(floors.items()))


def room_switches(hass: HomeAssistant, entry, control) -> list[RoomCleanSwitch]:
    floors = floor_rooms(entry)
    sig = _rooms_sig(floors)

    @callback
    def _rooms_changed() -> None:
        # New/removed rooms or floors after a map download: reload so the
        # switch set follows the map.
        if _rooms_sig(floor_rooms(entry)) != sig:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    coord = entry.runtime_data.map
    if getattr(coord, "is_saved_map", False):
        entry.async_on_unload(coord.async_add_listener(_rooms_changed))
    if not floors:
        return []
    batcher = RoomCleanBatcher(hass, entry, control)
    entry.async_on_unload(batcher.unload)
    multi = len(floors) > 1
    return [RoomCleanSwitch(control, entry, batcher, mid, floor, multi, rid, name or f"#{rid}")
            for mid, (floor, rooms) in floors.items()
            for rid, name in sorted(rooms.items())]
