"""Cleaning-session log built from local telemetry only.

The robot's own history prop (17.46) never answers over the LAN on firmware
4.5.6 (docs/MIOT_SPEC.md), and it reports no per-room completion either. What
it DOES report locally while it works is the task type (17.9), the task
targets (17.34: room ids / zone corners, [] = whole home), the session area
(17.27) and its status (2.2). This module folds those polls into one record
per task and compares the cleaned area with the area of the targeted rooms in
the saved map — the closest local answer to "which rooms got skipped".

`CleanSessionTracker` is pure (unit-tested without HA); `CleanLog` wires it to
the control coordinator, keeps a short history in HA storage, fires
`jonr_local_clean_finished` and raises a Repairs issue when the robot names a
room the saved map does not know (= the saved map is outdated).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

# 17.9 clean-type-status (spec v4): 0 None, 1 Idle; the rest are task states.
_IDLE_TASK = {0, 1}
_TASK_KIND = {
    2: "whole_home", 3: "whole_home", 4: "whole_home",
    5: "mapping", 6: "mapping", 7: "mapping",
    8: "rooms", 9: "rooms", 10: "rooms",
    11: "zones", 12: "zones", 13: "zones",
    14: "carpet", 15: "carpet", 16: "carpet",
    17: "spot", 18: "spot",
}
# 2.2 status codes that mean "heading back to the dock mid-task".
_RETURNING = {10, 12, 23}   # Go Charging, GoWash, GoDust
_DOCKED = {9, 13}           # Charging, Charged
# 17.9 "<kind> Pause" codes. A plain return-to-dock (16.1) leaves the task
# OPEN in pause on the dock (live 2026-11-06: 13 Charged + 9 Area Pause,
# resumable), so Idle never comes. Mid-task mop washes also dock the robot
# for ~2 min (HA history, nightly cleans), so a paused-on-dock task only
# counts as finished after PAUSED_ON_DOCK_END seconds.
_PAUSE_TASK = {3, 6, 9, 12, 15, 18}
PAUSED_ON_DOCK_END = 600
HISTORY_LEN = 30


def parse_targets(raw: Any) -> list:
    """17.34 clean-values -> list ([] when empty/unreadable)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return list(raw) if isinstance(raw, list) else []


class CleanSessionTracker:
    """Fold successive telemetry snapshots into one record per task (pure)."""

    def __init__(self, room_names: Callable[[], dict[int, str]],
                 room_area: Callable[[], dict[int, float]],
                 now: Callable[[], float] = time.time) -> None:
        self._room_names = room_names
        self._room_area = room_area
        self._now = now
        self._s: dict | None = None
        self._prev_status: int | None = None
        self._docked_pause_since: float | None = None
        self._closed_while_paused = False

    @property
    def active(self) -> dict | None:
        return self._s

    def feed(self, *, task: int | None, status: int | None, targets_raw: Any,
             area: int | None, minutes: int | None, fault: int | None,
             station_error: int | None, battery: int | None) -> dict | None:
        """Process one poll. Returns the finished session record, else None.

        A session ends on (a) 17.9 Idle, (b) the task sitting paused on the
        dock for PAUSED_ON_DOCK_END seconds (plain return-to-dock), or (c) a
        different task replacing it. After (b) the still-paused task is not
        re-opened until it moves again (resume or a new task).
        """
        if task is None:
            self._prev_status = status
            return None
        finished = None
        now = self._now()
        paused_on_dock = task in _PAUSE_TASK and status in _DOCKED

        if task in _IDLE_TASK:
            self._docked_pause_since = None
            self._closed_while_paused = False
            if self._s is not None:
                # 17.27 keeps the final session area after the task closes,
                # and a fault can surface on the closing poll: fold it in.
                self._absorb(area, minutes, fault, station_error, battery)
                finished = self._finish(status)
            self._prev_status = status
            return finished

        if paused_on_dock:
            if self._docked_pause_since is None:
                self._docked_pause_since = now
            if self._closed_while_paused or self._s is None:
                # Nothing is being cleaned: a paused task parked on the dock
                # (e.g. found at startup, or already closed) opens no session.
                self._prev_status = status
                return None
            if self._s is not None and now - self._docked_pause_since >= PAUSED_ON_DOCK_END:
                self._absorb(area, minutes, fault, station_error, battery)
                finished = self._finish(status)
                self._closed_while_paused = True
                self._prev_status = status
                return finished
        else:
            self._docked_pause_since = None
            self._closed_while_paused = False

        kind = _TASK_KIND.get(task, f"task_{task}")
        t_new = parse_targets(targets_raw)
        if self._s is not None and (
                kind != self._s["kind"]
                or (t_new and self._s["targets"] and t_new != self._s["targets"])):
            # A different task replaced the open one (xtl closes the old task
            # with a stop only ~2 s before the new start; a 10 s poll can
            # miss the Idle in between).
            finished = self._finish(self._prev_status)

        if self._s is None:
            self._s = {
                "started": now, "kind": kind, "task_codes": [], "targets": [],
                "area_max": 0, "minutes_max": 0, "returns": 0, "errors": [],
                "battery_min": battery,
            }
        s = self._s
        if task not in s["task_codes"]:
            s["task_codes"].append(task)
        if t_new:
            s["targets"] = t_new
        if status in _RETURNING and self._prev_status not in _RETURNING:
            s["returns"] += 1
        self._absorb(area, minutes, fault, station_error, battery)
        self._prev_status = status
        return finished

    def _absorb(self, area, minutes, fault, station_error, battery) -> None:
        s = self._s
        if isinstance(area, int):
            s["area_max"] = max(s["area_max"], area)
        if isinstance(minutes, int):
            s["minutes_max"] = max(s["minutes_max"], minutes)
        for code in (fault, station_error):
            if code and code not in s["errors"]:
                s["errors"].append(code)
        if isinstance(battery, int):
            s["battery_min"] = battery if s["battery_min"] is None else min(s["battery_min"], battery)

    def _finish(self, status: int | None) -> dict:
        s, self._s = self._s, None
        names, areas = self._room_names() or {}, self._room_area() or {}
        if s["kind"] == "rooms":
            room_ids = [int(r) for r in s["targets"] if isinstance(r, (int, str)) and str(r).isdigit()]
        elif s["kind"] == "whole_home":
            room_ids = sorted(names)
        else:
            room_ids = []
        unknown = [r for r in room_ids if names and r not in names]
        expected = round(sum(areas.get(r, 0.0) for r in room_ids), 1) if room_ids else None
        coverage = (round(100.0 * s["area_max"] / expected) if expected else None)
        # Robot area is integer m²; the raster area excludes furniture shadows
        # and walls the robot drives along, so a full clean can exceed 100 %.
        ended = self._now()
        return {
            "kind": s["kind"],
            "started": s["started"], "ended": ended,
            "duration_min": round((ended - s["started"]) / 60.0, 1),
            "robot_clean_time_s": s["minutes_max"],  # 17.26 counts seconds (live 2026-11-06)
            "room_ids": room_ids,
            "rooms": [names.get(r, f"#{r}") for r in room_ids],
            "unknown_room_ids": unknown,
            "zones": s["targets"] if s["kind"] == "zones" else [],
            "area_m2": s["area_max"],
            "expected_area_m2": expected,
            "coverage_pct": coverage,
            "dock_returns": s["returns"],
            "errors": s["errors"],
            "battery_min": s["battery_min"],
            "end_status": status,
            "ended_on_dock": status in _DOCKED,
            "task_codes": s["task_codes"],
        }


# --- Home Assistant wiring -------------------------------------------------------
class CleanLog:
    """Attach a CleanSessionTracker to the control coordinator."""

    def __init__(self, hass, entry, control, saved_map) -> None:
        from homeassistant.helpers.storage import Store

        from .const import DOMAIN

        self.hass = hass
        self.entry = entry
        self._control = control
        self._map = saved_map
        self._store = Store(hass, 1, f"{DOMAIN}_clean_log_{entry.entry_id}")
        self.history: list[dict] = []
        self._listeners: list[Callable[[], None]] = []
        self._unsub: Callable[[], None] | None = None
        self.tracker = CleanSessionTracker(self._names, self._areas)

    def _names(self) -> dict[int, str]:
        view = getattr(self._map, "view", None)
        return view.room_names if view else {}

    def _areas(self) -> dict[int, float]:
        view = getattr(self._map, "view", None)
        return view.room_area_m2 if view else {}

    @property
    def last(self) -> dict | None:
        return self.history[-1] if self.history else None

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    async def async_start(self) -> None:
        self.history = (await self._store.async_load() or {}).get("history", [])
        self._unsub = self._control.async_add_listener(self._on_update)

    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    def _on_update(self) -> None:
        d = self._control.data
        if d is None:
            return
        done = self.tracker.feed(
            task=d.robot_status_raw, status=d.raw_status, targets_raw=d.clean_values_raw,
            area=d.clean_area, minutes=d.clean_time, fault=d.fault,
            station_error=d.station_error_raw, battery=d.battery,
        )
        if done is not None:
            self.hass.async_create_task(self._async_finished(done))

    async def _async_finished(self, rec: dict) -> None:
        from homeassistant.helpers import issue_registry as ir

        from .const import DOMAIN, EVENT_CLEAN_FINISHED

        self.history = (self.history + [rec])[-HISTORY_LEN:]
        await self._store.async_save({"history": self.history})
        _LOGGER.info(
            "Clean finished: %s rooms=%s area=%s/%s m2 (%s%%) returns=%s errors=%s end_status=%s",
            rec["kind"], rec["rooms"], rec["area_m2"], rec["expected_area_m2"],
            rec["coverage_pct"], rec["dock_returns"], rec["errors"], rec["end_status"])
        self.hass.bus.async_fire(EVENT_CLEAN_FINISHED, {"entry_id": self.entry.entry_id, **rec})
        if rec["unknown_room_ids"]:
            ir.async_create_issue(
                self.hass, DOMAIN, f"saved_map_outdated_{self.entry.entry_id}",
                is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key="saved_map_outdated",
                translation_placeholders={"rooms": ", ".join(map(str, rec["unknown_room_ids"]))},
            )
        for cb in list(self._listeners):
            cb()
