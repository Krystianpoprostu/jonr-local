"""Push a saved map dump into Home Assistant (jonr_local.import_map), over the LAN.

    python tools/push_map.py vacuum.jonr_p20_pro [dump_dir]   # default dump: local_data/map_dumps/latest

Reads HA_URL / HA_TOKEN from .env (never printed). Only talks to your HA.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    entity_id = sys.argv[1]
    dump = (Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "local_data" / "map_dumps" / "latest").resolve()
    env = envfile.load()
    body = {
        "entity_id": entity_id,
        "map_raw": (dump / "map_raw.json").read_text(encoding="utf-8"),
        "source": f"tools/dump_map.py {dump.name}",
    }
    infos = dump / "map_infos_raw.json"
    if infos.exists():
        body["map_infos_raw"] = infos.read_text(encoding="utf-8")
    req = urllib.request.Request(
        f"{env['HA_URL'].rstrip('/')}/api/services/jonr_local/import_map?return_response",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {env['HA_TOKEN']}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        raise SystemExit(f"HA rejected the import: HTTP {err.code} {err.read()[:300]!r}")
    summary = out.get("service_response", {}).get(entity_id, out)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
