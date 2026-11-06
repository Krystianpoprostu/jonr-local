"""Read every readable MIoT property of the robot over LAN (read-only).
Writes full results to local_data/props_<ts>.json (gitignored); prints a redacted table."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile
from miio import MiotDevice

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.load(open(ROOT / "docs/spec/xtl.vacuum.xm2216.v4.json"))
SENSITIVE = {(1, 3), (1, 5)}  # serial-number, serial-no

def redact(siid, piid, v):
    if (siid, piid) in SENSITIVE: return "<redacted>"
    if isinstance(v, str) and re.search(r"[0-9a-fA-F]{32}", v): return "<redacted-hex>"
    return v

def main():
    env = envfile.load()
    dev = MiotDevice(env["MIIO_IP"], env["MIIO_TOKEN"], mapping={}, timeout=6)
    props = [(s["iid"], p["iid"], p["type"].split(":")[3]) for s in SPEC["services"]
             for p in s.get("properties", []) if "read" in p["access"]]
    results = {}
    for i in range(0, len(props), 3):
        chunk = props[i:i+3]
        req = [{"did": f"{s}-{p}", "siid": s, "piid": p} for s, p, _ in chunk]
        try:
            raw = dev.get_properties(req, property_getter="get_properties", max_properties=3)
            for r in raw:
                results[(r["siid"], r["piid"])] = {"code": r.get("code"), "value": r.get("value")}
        except Exception as e:
            for s, p, _ in chunk:
                results[(s, p)] = {"code": "timeout/err", "value": type(e).__name__}
        time.sleep(0.3)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "local_data"; out.mkdir(exist_ok=True)
    (out / f"props_{ts}.json").write_text(json.dumps(
        [{"siid": s, "piid": p, "name": n, **results.get((s, p), {})} for s, p, n in props],
        ensure_ascii=False, indent=1))
    for s, p, n in props:
        r = results.get((s, p), {})
        v = redact(s, p, r.get("value"))
        vs = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        if len(vs) > 90: vs = vs[:87] + "…"
        print(f"{s}.{p}\t{n}\tcode={r.get('code')}\t{vs}")
    print(f"saved local_data/props_{ts}.json")

main()
