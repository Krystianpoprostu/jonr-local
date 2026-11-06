"""One-shot map dump: ask the robot (LAN) for its map file names, fetch the files from the Mi cloud
ONCE (QR login, nothing persisted), save everything locally and render a PNG.

    python tools/dump_map.py [--out local_data/map_dumps]

Output: <out>/<timestamp>/ + <out>/latest symlink:
    map_raw.json        the KS3 map file exactly as downloaded (plain JSON; map 'fields' f0..f8)
    map_infos_raw.json  the KS3 map catalogue file (map names, saved flags)
    meta.json           when/what/which map, content hash, map names, firmware (no uid, no tokens)
    rooms.json          [{room_id, id, name, type, center, bbox, prefer}] - room_id is what 17.1 type 3 takes
    calibration.json    calibration points (map scene <-> image pixels) for zone coordinates
    attributes.json     full camera-attribute contract (what the HA map camera exposes)
    vector.json         vector contract for the bundled Lovelace card
    map.png             rendered image (render_map.py can redo it offline from map_raw.json)

The robot does NOT need internet: it names the files locally (17.12 / 17.13); this computer downloads them.
Reuses the integration's own code: cloud/connector.py (login, signed URL, download), xtl_map.py (decode,
render), spec/profiles/xtl.py (map-infos parsing). Secrets: the cloud session lives in memory only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COMP = ROOT / "custom_components" / "jonr_local"
sys.path.insert(0, str(HERE))
sys.path.append(str(COMP))  # appended: the integration's select.py must not shadow stdlib `select`

import envfile  # noqa: E402
from miio import MiotDevice  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


connector = load("jv_connector", COMP / "cloud" / "connector.py")
xtl_map = load("jv_xtl_map", COMP / "xtl_map.py")
from spec.profiles.xtl import xtl_parse_map_infos_catalog, xtl_parse_map_infos_file  # noqa: E402


def local_file_names(env) -> tuple[str, str]:
    dev = MiotDevice(env["MIIO_IP"], env["MIIO_TOKEN"], mapping={}, timeout=15)
    names = []
    for aiid, piid in ((12, 38), (13, 37)):
        res = dev.call_action_by(17, aiid, [])
        val = next((o.get("value") for o in res.get("out", []) if isinstance(o, dict) and o.get("piid") == piid), None)
        if not isinstance(val, str) or val.count("/") != 2:
            raise SystemExit(f"The robot returned no file name (17.{aiid}): {res}")
        names.append(val)
    fw = dev.info().firmware_version
    return names[0], names[1], fw


def qr_login() -> "connector.XiaomiCloud":
    """QR login through PiotrMachowski's Xiaomi-cloud-tokens-extractor (clone it to
    ../third_party/ or set TOKEN_EXTRACTOR), then hand the session to the integration's
    connector. The integration's own qr_begin/qr_poll did not complete in testing."""
    sys.argv = [sys.argv[0]]
    te = load("token_extractor", Path(os.environ.get("TOKEN_EXTRACTOR", ROOT.parent / "third_party" / "Xiaomi-cloud-tokens-extractor" / "token_extractor.py")))
    qc = te.QrCodeXiaomiCloudConnector()
    # unique URL per run: the browser must never show a cached QR from an earlier attempt
    qr_url = f"http://127.0.0.1:31415/qr-{int(time.time())}.png"
    print(f"QR code: {qr_url}  (Mi Home app → Profile → scan icon)", flush=True)
    subprocess.Popen(["sh", "-c", f"sleep 3; xdg-open {qr_url}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not qc.login():
        raise SystemExit("Login failed (QR code expired or rejected).")
    cloud = connector.XiaomiCloud("qr")
    cloud.restore_session(qc.userId, qc._ssecurity, qc._serviceToken, getattr(qc, "_pass_token", None))
    print("Logged in.", flush=True)
    return cloud


def fetch(cloud, server: str, did: str, obj: str) -> bytes:
    url = cloud.map_url(server, did, obj, "get_interim_file_url_pro", raw_obj=True)
    if not url:
        raise SystemExit("The cloud returned no download URL (session / region / no file uploaded yet).")
    raw = cloud.download(url)
    if not raw:
        raise SystemExit("Download failed.")
    return raw


def render_dump(dump: Path) -> dict:
    """Offline: map_raw.json -> map.png + attributes/vector/rooms/calibration. Returns the attributes."""
    raw = (dump / "map_raw.json").read_bytes()
    res = xtl_map.render_xtl_map(raw)
    if res is None:
        raise SystemExit("The map file holds no readable map.")
    attrs = dict(res["attributes"])
    attrs.pop("updated_at", None)
    (dump / "map.png").write_bytes(res["image_png"])
    (dump / "attributes.json").write_text(json.dumps(attrs, ensure_ascii=False, indent=1))
    (dump / "vector.json").write_text(json.dumps(res["vector"], ensure_ascii=False))
    (dump / "calibration.json").write_text(json.dumps(attrs.get("calibration_points"), indent=1))
    rooms = [{
        "room_id": int(rid), "id": r.get("id"), "name": r.get("name"), "type": r.get("type"),
        "center": [r.get("x"), r.get("y")],
        "bbox": [r.get("x0"), r.get("y0"), r.get("x1"), r.get("y1")],
        "prefer": r.get("prefer"),
    } for rid, r in sorted(attrs["rooms"].items(), key=lambda kv: int(kv[0]))]
    (dump / "rooms.json").write_text(json.dumps(rooms, ensure_ascii=False, indent=1))
    return attrs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "local_data" / "map_dumps"))
    a = ap.parse_args()
    env = envfile.load()
    server, did = env.get("XIAOMI_SERVER", "de"), env["MIIO_DID"]

    map_obj, infos_obj, fw = local_file_names(env)
    print(f"Robot (LAN): map file …/{map_obj.split('/', 1)[1]}, catalogue …/{infos_obj.split('/', 1)[1]}", flush=True)

    cloud = qr_login()
    raw_map = fetch(cloud, server, did, map_obj)
    raw_infos = fetch(cloud, server, did, infos_obj)
    del cloud  # session is never written anywhere

    dump = Path(a.out) / time.strftime("%Y%m%d-%H%M%S")
    dump.mkdir(parents=True)
    (dump / "map_raw.json").write_bytes(raw_map)
    (dump / "map_infos_raw.json").write_bytes(raw_infos)
    attrs = render_dump(dump)
    meta = {
        "dumped_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": env.get("MIIO_MODEL"), "firmware": fw, "server": server,
        "map_file_slot": map_obj.rsplit("/", 1)[1], "infos_file_slot": infos_obj.rsplit("/", 1)[1],
        "map_id": attrs.get("map_id"),
        "map_names": {str(k): v for k, v in xtl_parse_map_infos_file(raw_infos).items()},
        "map_catalog": xtl_parse_map_infos_catalog(raw_infos),
        "map_sha256": hashlib.sha256(raw_map).hexdigest(),
        "room_count": len(attrs.get("rooms", {})),
        "source": "cloud KS3 via get_interim_file_url_pro (one-shot)",
    }
    (dump / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    latest = Path(a.out) / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(dump.name)

    print(f"\nSaved: {dump}")
    print(f"map_id={meta['map_id']}  maps: {meta['map_names']}  rooms: {meta['room_count']}")
    for r in json.loads((dump / "rooms.json").read_text()):
        print(f"  room_id {r['room_id']}: {r['name']} (type {r['type']})")


if __name__ == "__main__":
    main()
