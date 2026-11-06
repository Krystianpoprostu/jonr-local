"""Stage 3: run the Stage-1 operation list against the robot (robot cut off from the internet).

Every write either re-sends the current value or is reverted; the robot moves twice (~15 s each)
and is always sent back to the dock. Destructive ops (consumable reset, map switch/delete) are skipped.

    python tools/offline_test.py <label> [--room ROOM_ID] [--zone X1 Y1 X2 Y2]
Without --room/--zone the robot does not move. Room ids and zone coordinates
(map scene units, 5 cm grid) come from your saved map (rooms.json / the map
camera attributes) — pick a small free area.
Results: local_data/offline_<label>_<ts>.json + markdown rows on stdout.
"""
import argparse
import json
import sys
import time
from pathlib import Path

_ap = argparse.ArgumentParser()
_ap.add_argument("label")
_ap.add_argument("--room", type=int)
_ap.add_argument("--zone", type=int, nargs=4)
ARGS = _ap.parse_args()
LABEL = ARGS.label
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv = [sys.argv[0], "none"]
import miio_probe  # noqa: E402
import motion_test as m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
results = []


def step(name, kind, fn):
    t = time.time()
    try:
        detail = fn()
        ok = detail is not False
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {str(e)[:80]}"
    results.append({"op": name, "kind": kind, "ok": ok, "detail": detail, "secs": round(time.time() - t, 1)})
    print(f"| {name} | {kind} | {'✅' if ok else '❌'} | {detail} | {time.time()-t:.1f}s |", flush=True)


def read(props):
    raw = m.dev.get_properties([{"did": f"{s}-{p}", "siid": s, "piid": p} for s, p in props],
                               property_getter="get_properties", max_properties=len(props))
    bad = [f"{r['siid']}.{r['piid']}" for r in raw if r.get("code") != 0]
    if bad:
        raise RuntimeError(f"codes!=0 for {bad}")
    return {(r["siid"], r["piid"]): r.get("value") for r in raw}


def act_ok(aiid, params=(), siid=17):
    r = m.dev.call_action_by(siid, aiid, list(params))
    if r.get("code") != 0:
        raise RuntimeError(f"code {r.get('code')}")
    return f"{siid}.{aiid} code 0"


def wait_status(targets, secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            v = read([(2, 2), (17, 9), (17, 34)])
            if v[(2, 2)] in targets:
                return v
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    raise RuntimeError(f"status not in {targets} within {secs}s")


def motion(start, expect_task):
    m.dev.call_action_by(17, 3, [])
    time.sleep(2)
    try:
        act_ok(1, [m.p(8, start[0]), m.p(34, start[1])])
        v = wait_status({7, 17}, 15)          # Sweeping / Relocation = it left the dock
        task, target = v[(17, 9)], v[(17, 34)]
        time.sleep(10)
        if task != expect_task:
            raise RuntimeError(f"task {task} != {expect_task}")
        return f"task={task} clean_values={target}"
    finally:
        m.dev.call_action_by(17, 3, [])
        time.sleep(2)
        m.dev.call_action_by(16, 1, [])


def main():
    env = m.env
    print(f"Run {LABEL} at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    print("| operation | kind | result | details | time |\n|---|---|---|---|---|")
    step("miIO.info", "read", lambda: miio_probe.call(env["MIIO_IP"], env["MIIO_TOKEN"], "miIO.info")["result"]["model"])
    step("status/battery/errors (2.2, 16.1, 17.35, 17.79, 17.36)", "read",
         lambda: str(read([(2, 2), (16, 1), (17, 35), (17, 79), (17, 36)]).values()))
    step("modes (17.10, 17.12, 17.13, 17.14, 17.65)", "read",
         lambda: str(list(read([(17, 10), (17, 12), (17, 13), (17, 14), (17, 65)]).values())))
    step("consumables (17.32)", "read", lambda: f"{len(json.loads(read([(17, 32)])[(17, 32)]))} items")
    step("station (17.49, 17.48, 17.51-54)", "read",
         lambda: str(list(read([(17, 49), (17, 48), (17, 51), (17, 52), (17, 53), (17, 54)]).values())))
    step("DND (17.19), timers (17.17)", "read", lambda: str(list(read([(17, 19), (17, 17)]).values())))
    step("map file name (17.12)", "action-read",
         lambda: str(m.dev.call_action_by(17, 12, []).get("out", [{}])[0].get("value", "")).split("/", 1)[-1])
    step("map catalogue name (17.13)", "action-read",
         lambda: str(m.dev.call_action_by(17, 13, []).get("out", [{}])[0].get("value", "")).split("/", 1)[-1])

    cur = read([(17, 13), (17, 12), (17, 10), (17, 15), (17, 6), (17, 19)])
    step("fan = same value (17.26)", "write", lambda: act_ok(26, [m.p(13, cur[(17, 13)])]))
    step("water = same value (17.27)", "write", lambda: act_ok(27, [m.p(12, cur[(17, 12)])]))
    step("mode = same value (17.46)", "write", lambda: act_ok(46, [m.p(10, cur[(17, 10)])]))
    step("volume = same value (17.31)", "write", lambda: act_ok(31, [m.p(15, cur[(17, 15)])]))

    def child_lock_toggle():
        orig = bool(cur[(17, 6)])
        act_ok(36, [m.p(6, not orig)])
        time.sleep(2)
        flipped = read([(17, 6)])[(17, 6)]
        act_ok(36, [m.p(6, orig)])
        time.sleep(2)
        back = read([(17, 6)])[(17, 6)]
        if bool(flipped) == orig or bool(back) != orig:
            raise RuntimeError(f"flip={flipped} back={back}")
        return f"{int(orig)}→{int(flipped)}→{int(back)}"
    step("child lock toggle and restore (17.36)", "write", child_lock_toggle)
    step("DND window = same value (17.30)", "write", lambda: act_ok(30, [m.p(18, cur[(17, 19)])]))
    step("locate (17.4)", "action", lambda: act_ok(4))

    def dry_start_stop():
        act_ok(41, [m.p(4, True)])
        time.sleep(4)
        st = read([(17, 49)])[(17, 49)]
        act_ok(41, [m.p(4, False)])
        time.sleep(3)
        return f"after start 17.49={st}, after stop={read([(17, 49)])[(17, 49)]}"
    step("station: mop drying start/stop (17.41)", "action", dry_start_stop)

    if ARGS.room is not None:
        step(f"room clean {ARGS.room} (17.1 type 3)", "move", lambda: motion((3, f"[{ARGS.room}]"), 8))
        step("return to dock (16.1)", "move", lambda: f"status={wait_status({9, 13}, 150)[(2, 2)]}")
    if ARGS.zone:
        x1, y1, x2, y2 = ARGS.zone
        step("zone clean (17.1 type 4)", "move",
             lambda: motion((4, json.dumps([x1, y1, x2, y1, x2, y2, x1, y2])), 11))
        step("return to dock (16.1)", "move", lambda: f"status={wait_status({9, 13}, 150)[(2, 2)]}")

    out = ROOT / "local_data" / f"offline_{LABEL}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    print(f"\n{sum(r['ok'] for r in results)}/{len(results)} OK, saved {out.name}")


main()
