"""Short, supervised local command tests (robot MOVES for A/B). Always stops + docks.

    python tools/motion_test.py room 6           # A: clean room_id 6 (~20 s)
    python tools/motion_test.py zone 402 373 422 393   # B: clean one rect (scene units)
    python tools/motion_test.py write-same <map_id> <room_id> <name> <category> K F W C D   # C
    python tools/motion_test.py watch <seconds>  # read-only monitor
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402
from miio import MiotDevice  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.load(open(ROOT / "docs/spec/xtl.vacuum.xm2216.v4.json"))


def enum(siid, piid):
    for s in SPEC["services"]:
        if s["iid"] == siid:
            for p in s["properties"]:
                if p["iid"] == piid:
                    return {v["value"]: v["description"] for v in p.get("value-list", [])}
    return {}


STATUS, CTS = enum(2, 2), enum(17, 9)
WATCH = [(2, 2), (17, 9), (17, 34), (17, 49), (17, 35), (17, 76)]

env = envfile.load()
dev = MiotDevice(env["MIIO_IP"], env["MIIO_TOKEN"], mapping={}, timeout=15)


def act(aiid, params=(), siid=17):
    t = time.time()
    try:
        r = dev.call_action_by(siid, aiid, list(params))
        print(f"  action {siid}.{aiid} -> code={r.get('code')} ({time.time()-t:.1f}s)")
        return r
    except Exception as e:  # noqa: BLE001
        print(f"  action {siid}.{aiid} -> ERROR {type(e).__name__}: {e} ({time.time()-t:.1f}s)")
        return None


def p(piid, value):
    return {"did": "-", "piid": piid, "value": value}


def snapshot(tag=""):
    try:
        raw = dev.get_properties([{"did": f"{s}-{q}", "siid": s, "piid": q} for s, q in WATCH],
                                 property_getter="get_properties", max_properties=6)
        v = {(r["siid"], r["piid"]): r.get("value") for r in raw}
    except Exception as e:  # noqa: BLE001
        print(f"  [{tag}] read error {type(e).__name__}")
        return {}
    st, ct = v.get((2, 2)), v.get((17, 9))
    print(f"  [{tag}] status={st}:{STATUS.get(st)} task={ct}:{CTS.get(ct)} "
          f"clean_values={v.get((17, 34))!r} station={v.get((17, 49))} err={v.get((17, 35))} "
          f"room_edit={v.get((17, 76))!r}")
    return v


def watch(seconds, step=2.0, tag="t"):
    t0 = time.time()
    while time.time() - t0 < seconds:
        snapshot(f"{tag}+{time.time()-t0:4.0f}s")
        time.sleep(step)


def stop_and_dock():
    print("-> stop (17.3) + dock (16.1)")
    act(3)
    time.sleep(2)
    act(1, siid=16)
    watch(8, tag="dock")


def run_motion(start_params, label):
    print(f"== {label}")
    snapshot("before")
    try:
        print("-> stop-and-settle (17.3), as the integration does")
        act(3)
        time.sleep(2)
        print(f"-> start-clean 17.1 {start_params}")
        act(1, [p(8, start_params[0]), p(34, start_params[1])])
        watch(20)
    finally:
        stop_and_dock()


def main():
    cmd = sys.argv[1]
    if cmd == "room":
        ids = [int(x) for x in sys.argv[2:]]
        run_motion((3, json.dumps(ids)), f"A: room clean {ids}")
    elif cmd == "zone":
        x1, y1, x2, y2 = (int(v) for v in sys.argv[2:6])
        flat = [x1, y1, x2, y1, x2, y2, x1, y2]
        run_motion((4, json.dumps(flat)), f"B: zone clean {flat}")
    elif cmd == "write-same":
        map_id, room_id, name, cat = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
        k, f, w, c, d = (int(v) for v in sys.argv[6:11])
        print("== C1: 17.15 edite-area-info, same name/category")
        snapshot("before")
        act(15, [p(60, json.dumps({"mapId": map_id, "rooms": [
            {"roomId": room_id, "name": name, "category": cat}]}, separators=(",", ":"),
            ensure_ascii=False))])
        watch(6, tag="c1")
        print("== C2: 17.53 customization-rooms type 1, same preferences")
        payload = json.dumps({"total": 1, "index": 0, "customdata": {"type": 1, "data": [
            {"I": map_id, "R": room_id, "K": k, "F": f, "W": w, "C": c, "D": d}]}},
            separators=(",", ":"))
        act(53, [p(70, payload)])
        watch(6, tag="c2")
    elif cmd == "watch":
        watch(float(sys.argv[2]))
    elif cmd == "dock":
        stop_and_dock()


if __name__ == "__main__":
    main()
